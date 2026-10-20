#include "runsupervisor.h"

#include <QCoreApplication>
#include <QDir>
#include <QEventLoop>
#include <QFile>
#include <QHostAddress>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QRegularExpression>
#include <QStandardPaths>
#include <QTcpServer>
#include <QTimer>
#include <QUrl>
#include <QUuid>

namespace {
const QString kContract = QStringLiteral("1");

QString joinPath(const QString &root, const QString &leaf)
{
    return QDir(root).filePath(leaf);
}
}

EventLog::EventLog(QObject *parent) : QAbstractListModel(parent) {}

int EventLog::rowCount(const QModelIndex &parent) const
{
    return parent.isValid() ? 0 : m_rows.size();
}

QVariant EventLog::data(const QModelIndex &index, int role) const
{
    if (!index.isValid() || index.row() < 0 || index.row() >= m_rows.size())
        return {};
    const Row &row = m_rows.at(index.row());
    switch (role) {
    case KindRole: return row.kind;
    case MessageRole: return row.message;
    case StepRole: return row.step;
    case ShotRole: return row.shot;
    case UrlRole: return row.url;
    default: return {};
    }
}

QHash<int, QByteArray> EventLog::roleNames() const
{
    return {
        {KindRole, "kind"},
        {MessageRole, "message"},
        {StepRole, "step"},
        {ShotRole, "shot"},
        {UrlRole, "url"},
    };
}

void EventLog::append(const QJsonObject &event)
{
    const int row = m_rows.size();
    beginInsertRows(QModelIndex(), row, row);
    Row item;
    item.kind = event.value(QStringLiteral("kind")).toString();
    item.message = event.value(QStringLiteral("message")).toString();
    item.step = event.value(QStringLiteral("step")).toInt();
    item.shot = event.value(QStringLiteral("screenshotPath")).toString();
    item.url = event.value(QStringLiteral("url")).toString();
    m_rows.append(item);
    endInsertRows();
}

void EventLog::clear()
{
    beginResetModel();
    m_rows.clear();
    endResetModel();
}

QString EventLog::shotAt(int row) const
{
    if (row < 0 || row >= m_rows.size())
        return {};
    return m_rows.at(row).shot;
}

BugList::BugList(QObject *parent) : QAbstractListModel(parent) {}

int BugList::rowCount(const QModelIndex &parent) const
{
    return parent.isValid() ? 0 : m_bugs.size();
}

QVariant BugList::data(const QModelIndex &index, int role) const
{
    if (!index.isValid() || index.row() < 0 || index.row() >= m_bugs.size())
        return {};
    const QJsonObject bug = m_bugs.at(index.row());
    switch (role) {
    case TitleRole: return bug.value(QStringLiteral("title")).toString();
    case SeverityRole: return bug.value(QStringLiteral("severity")).toString();
    case SummaryRole:
        return bug.value(QStringLiteral("request")).toObject().value(QStringLiteral("status")).toInt();
    default: return {};
    }
}

QHash<int, QByteArray> BugList::roleNames() const
{
    return {
        {TitleRole, "title"},
        {SeverityRole, "severity"},
        {SummaryRole, "statusCode"},
    };
}

void BugList::setBugs(const QList<QJsonObject> &bugs)
{
    beginResetModel();
    m_bugs = bugs;
    endResetModel();
}

QVariantMap BugList::detailAt(int row) const
{
    QVariantMap detail;
    if (row < 0 || row >= m_bugs.size())
        return detail;
    const QJsonObject bug = m_bugs.at(row);
    const QJsonObject request = bug.value(QStringLiteral("request")).toObject();
    detail.insert(QStringLiteral("title"), bug.value(QStringLiteral("title")).toString());
    detail.insert(QStringLiteral("severity"), bug.value(QStringLiteral("severity")).toString());
    detail.insert(QStringLiteral("expected"), bug.value(QStringLiteral("expected")).toString());
    detail.insert(QStringLiteral("actual"), bug.value(QStringLiteral("actual")).toString());
    detail.insert(QStringLiteral("shot"), bug.value(QStringLiteral("screenshotPath")).toString());
    detail.insert(QStringLiteral("method"), request.value(QStringLiteral("method")).toString());
    detail.insert(QStringLiteral("requestUrl"), request.value(QStringLiteral("url")).toString());
    detail.insert(QStringLiteral("status"), request.value(QStringLiteral("status")).toInt());
    QStringList steps;
    for (const QJsonValue &step : bug.value(QStringLiteral("reproSteps")).toArray())
        steps.append(step.toString());
    detail.insert(QStringLiteral("steps"), steps);
    return detail;
}

RunSupervisor::RunSupervisor(QObject *parent)
    : QObject(parent)
    , m_events(new EventLog(this))
    , m_bugs(new BugList(this))
{
    connect(&m_proc, &QProcess::readyReadStandardError, this, [this] {
        const QString text = redactLine(QString::fromUtf8(m_proc.readAllStandardError()));
        for (const QString &line : text.split(QRegularExpression(QStringLiteral("[\\r\\n]+")), Qt::SkipEmptyParts))
            m_events->append(QJsonObject{
                {QStringLiteral("kind"), QStringLiteral("status")},
                {QStringLiteral("message"), QStringLiteral("daemon: ") + line},
                {QStringLiteral("step"), 0},
            });
    });
    connect(&m_proc, QOverload<int, QProcess::ExitStatus>::of(&QProcess::finished), this, [this](int code, QProcess::ExitStatus) {
        if (m_quitting)
            return;
        if (m_running) {
            fail(QStringLiteral("демон завершился, код %1").arg(code));
            setRunning(false);
        }
    });
}

RunSupervisor::~RunSupervisor()
{
    shutdown();
}

bool RunSupervisor::hasApiKey() const
{
    return !m_vault.load().isEmpty();
}

void RunSupervisor::setShellPath(const QString &value)
{
    if (m_shellPath == value)
        return;
    m_shellPath = value;
    emit shellPathChanged();
}

void RunSupervisor::setExePath(const QString &value)
{
    if (m_exePath == value)
        return;
    m_exePath = value;
    emit exePathChanged();
}

void RunSupervisor::setTask(const QString &value)
{
    if (m_task == value)
        return;
    m_task = value;
    emit taskChanged();
}

void RunSupervisor::setProvider(const QString &value)
{
    if (m_provider == value)
        return;
    m_provider = value;
    emit providerChanged();
}

void RunSupervisor::setModel(const QString &value)
{
    if (m_model == value)
        return;
    m_model = value;
    emit modelChanged();
}

void RunSupervisor::setBaseUrl(const QString &value)
{
    if (m_baseUrl == value)
        return;
    m_baseUrl = value;
    emit baseUrlChanged();
}

void RunSupervisor::setMaxSteps(int value)
{
    const int clamped = qBound(5, value, 40);
    if (m_maxSteps == clamped)
        return;
    m_maxSteps = clamped;
    emit maxStepsChanged();
}

void RunSupervisor::setAllowLogin(bool value)
{
    if (m_allowLogin == value)
        return;
    m_allowLogin = value;
    emit allowLoginChanged();
}

void RunSupervisor::setAllowLaunch(bool value)
{
    if (m_allowLaunch == value)
        return;
    m_allowLaunch = value;
    emit allowLaunchChanged();
}

void RunSupervisor::setAllowPayments(bool value)
{
    if (m_allowPayments == value)
        return;
    m_allowPayments = value;
    emit allowPaymentsChanged();
}

void RunSupervisor::setFidelity(const QString &value)
{
    if (value != QLatin1String("vision") && value != QLatin1String("log-only"))
        return;
    if (m_fidelity == value)
        return;
    m_fidelity = value;
    emit fidelityChanged();
}

void RunSupervisor::startRun(const QString &apiKey)
{
    if (m_running || m_quitting)
        return;
    if (!apiKey.trimmed().isEmpty()) {
        m_vault.save(apiKey.toUtf8());
        emit hasApiKeyChanged();
    }
    if (!QFileInfo(m_shellPath).isDir()) {
        setStatus(QStringLiteral("Каталог шела не найден"));
        return;
    }
    if (!m_exePath.isEmpty() && !QFileInfo(m_exePath).isFile()) {
        setStatus(QStringLiteral("Файл шела не найден"));
        return;
    }
    if (m_task.trimmed().isEmpty()) {
        setStatus(QStringLiteral("Нужен текст сценария"));
        return;
    }
    m_events->clear();
    m_bugs->setBugs({});
    m_bugDetail.clear();
    emit bugDetailChanged();
    setPreview({});
    m_runId.clear();
    m_traceDir.clear();
    setRunning(true);
    if (m_proc.state() == QProcess::NotRunning) {
        if (!startDaemon()) {
            setRunning(false);
            return;
        }
        m_healthTries = 0;
        QTimer::singleShot(200, this, &RunSupervisor::pollHealth);
        return;
    }
    postRun();
}

void RunSupervisor::cancelRun()
{
    if (m_runId.isEmpty())
        return;
    QNetworkRequest request(daemonUrl(QStringLiteral("/runs/%1/cancel").arg(m_runId)));
    request.setRawHeader("Authorization", QByteArray("Bearer ") + m_token.toUtf8());
    m_nam.post(request, QByteArray());
    setStatus(QStringLiteral("Останавливаю прогон"));
}

void RunSupervisor::shutdown()
{
    if (m_quitting)
        return;
    m_quitting = true;
    if (!m_runId.isEmpty() && m_proc.state() != QProcess::NotRunning) {
        QNetworkRequest request(daemonUrl(QStringLiteral("/runs/%1/cancel").arg(m_runId)));
        request.setRawHeader("Authorization", QByteArray("Bearer ") + m_token.toUtf8());
        QNetworkReply *reply = m_nam.post(request, QByteArray());
        QEventLoop loop;
        QTimer timer;
        timer.setSingleShot(true);
        connect(reply, &QNetworkReply::finished, &loop, &QEventLoop::quit);
        connect(&timer, &QTimer::timeout, &loop, &QEventLoop::quit);
        timer.start(800);
        loop.exec();
        reply->deleteLater();
    }
    if (m_eventsReply) {
        m_eventsReply->abort();
        m_eventsReply = nullptr;
    }
    if (m_proc.state() != QProcess::NotRunning) {
        m_proc.kill();
        m_proc.waitForFinished(1500);
    }
}

void RunSupervisor::selectEvent(int row)
{
    setPreview(m_events->shotAt(row));
}

void RunSupervisor::selectBug(int row)
{
    m_bugDetail = m_bugs->detailAt(row);
    const QString shot = m_bugDetail.value(QStringLiteral("shot")).toString();
    if (!shot.isEmpty() && QFileInfo::exists(shot))
        m_bugDetail.insert(QStringLiteral("shotUrl"), QUrl::fromLocalFile(shot).toString());
    emit bugDetailChanged();
    setPreview(shot);
}

RunSupervisor::LaunchPaths RunSupervisor::locateAgent() const
{
    LaunchPaths found;
    QDir dir(QCoreApplication::applicationDirPath());
    for (int hop = 0; hop < 6; ++hop) {
        const QString mainPy = dir.filePath(QStringLiteral("agent/shellagent/__main__.py"));
        if (QFileInfo::exists(mainPy)) {
            found.projectRoot = dir.absolutePath();
            found.agentDir = dir.filePath(QStringLiteral("agent"));
            break;
        }
        if (!dir.cdUp())
            break;
    }
    const QStringList candidates = {
        joinPath(found.agentDir, QStringLiteral(".venv/Scripts/python.exe")),
        joinPath(found.agentDir, QStringLiteral(".venv/bin/python.exe")),
        QStringLiteral("C:/msys64/mingw64/bin/python.exe"),
    };
    for (const QString &candidate : candidates) {
        if (QFileInfo::exists(candidate)) {
            found.python = candidate;
            break;
        }
    }
    if (found.python.isEmpty())
        found.python = QStringLiteral("python");
    return found;
}

bool RunSupervisor::startDaemon()
{
    m_paths = locateAgent();
    if (m_paths.agentDir.isEmpty()) {
        fail(QStringLiteral("Не найден каталог agent рядом с приложением"));
        return false;
    }
    QTcpServer probe;
    if (!probe.listen(QHostAddress::LocalHost, 0)) {
        fail(QStringLiteral("Не удалось выбрать локальный порт"));
        return false;
    }
    m_port = probe.serverPort();
    probe.close();
    m_token = QUuid::createUuid().toString(QUuid::Id128);

    QProcessEnvironment env = QProcessEnvironment::systemEnvironment();
    env.insert(QStringLiteral("PYTHONPATH"), m_paths.agentDir);
    env.insert(QStringLiteral("PYTHONUNBUFFERED"), QStringLiteral("1"));
    env.insert(QStringLiteral("PYTHONIOENCODING"), QStringLiteral("utf-8"));
    env.insert(QStringLiteral("SHELLA_PORT"), QString::number(m_port));
    env.insert(QStringLiteral("SHELLA_TOKEN"), m_token);
    env.insert(QStringLiteral("SHELLA_TRACE_ROOT"), joinPath(m_paths.projectRoot, QStringLiteral("traces")));
    const QString pythonDir = QFileInfo(m_paths.python).absolutePath();
    env.insert(QStringLiteral("PATH"), pythonDir + QDir::listSeparator() + env.value(QStringLiteral("PATH")));

    m_proc.setProcessEnvironment(env);
    m_proc.setWorkingDirectory(m_paths.projectRoot);
    m_proc.setProgram(m_paths.python);
    m_proc.setArguments({QStringLiteral("-m"), QStringLiteral("shellagent")});
    m_proc.start();
    if (!m_proc.waitForStarted(3000)) {
        fail(QStringLiteral("Не удалось запустить Python-демон"));
        return false;
    }
    setStatus(QStringLiteral("Демон запускается"));
    return true;
}

QUrl RunSupervisor::daemonUrl(const QString &path) const
{
    return QUrl(QStringLiteral("http://127.0.0.1:%1%2").arg(m_port).arg(path));
}

void RunSupervisor::pollHealth()
{
    if (m_quitting || m_proc.state() == QProcess::NotRunning)
        return;
    QNetworkRequest request(daemonUrl(QStringLiteral("/health")));
    request.setRawHeader("Authorization", QByteArray("Bearer ") + m_token.toUtf8());
    QNetworkReply *reply = m_nam.get(request);
    connect(reply, &QNetworkReply::finished, this, [this, reply] {
        reply->deleteLater();
        if (m_quitting)
            return;
        const QJsonObject body = QJsonDocument::fromJson(reply->readAll()).object();
        if (reply->error() == QNetworkReply::NoError && body.value(QStringLiteral("ok")).toBool()) {
            if (body.value(QStringLiteral("contractVersion")).toString() != kContract) {
                fail(QStringLiteral("Версия контракта демона не совпадает"));
                m_proc.kill();
                setRunning(false);
                return;
            }
            postRun();
            return;
        }
        if (++m_healthTries > 25) {
            fail(QStringLiteral("Демон не ответил на /health"));
            setRunning(false);
            return;
        }
        QTimer::singleShot(200, this, &RunSupervisor::pollHealth);
    });
}

void RunSupervisor::postRun()
{
    QJsonObject llm;
    llm.insert(QStringLiteral("provider"), m_provider);
    llm.insert(QStringLiteral("model"), m_model);
    llm.insert(QStringLiteral("baseUrl"), m_baseUrl);
    QJsonObject policy;
    policy.insert(QStringLiteral("allowLogin"), m_allowLogin);
    policy.insert(QStringLiteral("allowLaunch"), m_allowLaunch);
    policy.insert(QStringLiteral("allowPayments"), m_allowPayments);
    QJsonObject body;
    body.insert(QStringLiteral("shellPath"), m_shellPath);
    body.insert(QStringLiteral("exePath"), m_exePath);
    body.insert(QStringLiteral("task"), m_task);
    body.insert(QStringLiteral("maxSteps"), m_maxSteps);
    body.insert(QStringLiteral("llm"), llm);
    body.insert(QStringLiteral("policy"), policy);
    body.insert(QStringLiteral("fidelity"), m_fidelity);

    QNetworkRequest request(daemonUrl(QStringLiteral("/runs")));
    request.setHeader(QNetworkRequest::ContentTypeHeader, QStringLiteral("application/json"));
    request.setRawHeader("Authorization", QByteArray("Bearer ") + m_token.toUtf8());
    QByteArray key = m_vault.load();
    if (!key.isEmpty())
        request.setRawHeader("X-Api-Key", key);
    key.fill('\0');

    QNetworkReply *reply = m_nam.post(request, QJsonDocument(body).toJson(QJsonDocument::Compact));
    connect(reply, &QNetworkReply::finished, this, [this, reply] {
        reply->deleteLater();
        if (m_quitting)
            return;
        const QJsonObject payload = QJsonDocument::fromJson(reply->readAll()).object();
        if (reply->error() != QNetworkReply::NoError) {
            const QString message = payload.value(QStringLiteral("error")).toString();
            fail(message.isEmpty() ? QStringLiteral("Не удалось начать прогон") : message);
            setRunning(false);
            return;
        }
        m_runId = payload.value(QStringLiteral("runId")).toString();
        m_traceDir = payload.value(QStringLiteral("traceDir")).toString();
        setStatus(QStringLiteral("Прогон %1").arg(m_runId));
        openEvents();
    });
}

void RunSupervisor::openEvents()
{
    if (m_eventsReply) {
        QNetworkReply *previous = m_eventsReply;
        m_eventsReply = nullptr;
        previous->abort();
    }
    m_stream.clear();
    QNetworkRequest request(daemonUrl(QStringLiteral("/events")));
    request.setRawHeader("Authorization", QByteArray("Bearer ") + m_token.toUtf8());
    QNetworkReply *reply = m_nam.get(request);
    m_eventsReply = reply;
    connect(reply, &QNetworkReply::readyRead, this, [this, reply] {
        if (m_eventsReply == reply)
            consumeEvents();
    });
    connect(reply, &QNetworkReply::finished, this, [this, reply] {
        if (m_eventsReply == reply)
            consumeEvents();
        const bool canceled = reply->error() == QNetworkReply::OperationCanceledError;
        if (m_eventsReply == reply && !m_quitting && !canceled && m_running) {
            fail(QStringLiteral("Поток событий закрылся"));
            setRunning(false);
            reloadBugs();
        }
        if (m_eventsReply == reply)
            m_eventsReply = nullptr;
        reply->deleteLater();
    });
}

void RunSupervisor::consumeEvents()
{
    if (!m_eventsReply)
        return;
    m_stream += m_eventsReply->readAll();
    while (true) {
        const int nl = m_stream.indexOf('\n');
        if (nl < 0)
            break;
        const QByteArray line = m_stream.left(nl).trimmed();
        m_stream.remove(0, nl + 1);
        if (line.isEmpty())
            continue;
        const QJsonObject event = QJsonDocument::fromJson(line).object();
        if (event.isEmpty())
            continue;
        m_events->append(event);
        handleEvent(event);
    }
}

void RunSupervisor::handleEvent(const QJsonObject &event)
{
    const QString shot = event.value(QStringLiteral("screenshotPath")).toString();
    if (!shot.isEmpty())
        setPreview(shot);
    const QString kind = event.value(QStringLiteral("kind")).toString();
    const QString message = event.value(QStringLiteral("message")).toString();
    if (kind == QLatin1String("bug") || kind == QLatin1String("done") || kind == QLatin1String("error"))
        reloadBugs();
    if (kind == QLatin1String("done") || kind == QLatin1String("error"))
        setRunning(false);
    if (kind == QLatin1String("status") && (message == QLatin1String("stopped") || message == QLatin1String("cancelled"))) {
        setRunning(false);
        reloadBugs();
    }
    if (kind == QLatin1String("status") || kind == QLatin1String("error") || kind == QLatin1String("done"))
        setStatus(message);
}

void RunSupervisor::reloadBugs()
{
    if (m_traceDir.isEmpty())
        return;
    QFile file(QDir(m_traceDir).filePath(QStringLiteral("bugs.json")));
    if (!file.open(QIODevice::ReadOnly))
        return;
    const QJsonArray array = QJsonDocument::fromJson(file.readAll()).array();
    QList<QJsonObject> bugs;
    for (const QJsonValue &value : array) {
        if (value.isObject())
            bugs.append(value.toObject());
    }
    m_bugs->setBugs(bugs);
    if (!bugs.isEmpty())
        selectBug(bugs.size() - 1);
}

void RunSupervisor::setRunning(bool value)
{
    if (m_running == value)
        return;
    m_running = value;
    emit runningChanged();
}

void RunSupervisor::setStatus(const QString &text)
{
    if (m_statusText == text)
        return;
    m_statusText = text;
    emit statusTextChanged();
}

void RunSupervisor::setPreview(const QString &path)
{
    QString url;
    if (!path.isEmpty() && QFileInfo::exists(path))
        url = QUrl::fromLocalFile(path).toString();
    if (m_previewUrl == url)
        return;
    m_previewUrl = url;
    emit previewUrlChanged();
}

void RunSupervisor::fail(const QString &text)
{
    setStatus(text);
    m_events->append(QJsonObject{
        {QStringLiteral("kind"), QStringLiteral("error")},
        {QStringLiteral("message"), text},
        {QStringLiteral("step"), 0},
    });
}

QString RunSupervisor::redactLine(const QString &line) const
{
    QString masked = line;
    masked.replace(QRegularExpression(QStringLiteral("(?i)Bearer\\s+\\S+")), QStringLiteral("Bearer ***"));
    masked.replace(QRegularExpression(QStringLiteral("sk-[A-Za-z0-9]+")), QStringLiteral("sk-***"));
    return masked;
}
