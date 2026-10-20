#pragma once

#include "secretvault.h"

#include <QAbstractListModel>
#include <QJsonObject>
#include <QNetworkAccessManager>
#include <QProcess>

class QNetworkReply;

class EventLog : public QAbstractListModel
{
    Q_OBJECT
public:
    enum Roles { KindRole = Qt::UserRole + 1, MessageRole, StepRole, ShotRole, UrlRole };
    explicit EventLog(QObject *parent = nullptr);
    int rowCount(const QModelIndex &parent = QModelIndex()) const override;
    QVariant data(const QModelIndex &index, int role) const override;
    QHash<int, QByteArray> roleNames() const override;
    void append(const QJsonObject &event);
    void clear();
    QString shotAt(int row) const;

private:
    struct Row {
        QString kind;
        QString message;
        int step = 0;
        QString shot;
        QString url;
    };
    QList<Row> m_rows;
};

class BugList : public QAbstractListModel
{
    Q_OBJECT
public:
    enum Roles { TitleRole = Qt::UserRole + 1, SeverityRole, SummaryRole };
    explicit BugList(QObject *parent = nullptr);
    int rowCount(const QModelIndex &parent = QModelIndex()) const override;
    QVariant data(const QModelIndex &index, int role) const override;
    QHash<int, QByteArray> roleNames() const override;
    void setBugs(const QList<QJsonObject> &bugs);
    QVariantMap detailAt(int row) const;

private:
    QList<QJsonObject> m_bugs;
};

class RunSupervisor : public QObject
{
    Q_OBJECT
    Q_PROPERTY(QString shellPath READ shellPath WRITE setShellPath NOTIFY shellPathChanged)
    Q_PROPERTY(QString exePath READ exePath WRITE setExePath NOTIFY exePathChanged)
    Q_PROPERTY(QString task READ task WRITE setTask NOTIFY taskChanged)
    Q_PROPERTY(QString provider READ provider WRITE setProvider NOTIFY providerChanged)
    Q_PROPERTY(QString model READ model WRITE setModel NOTIFY modelChanged)
    Q_PROPERTY(QString baseUrl READ baseUrl WRITE setBaseUrl NOTIFY baseUrlChanged)
    Q_PROPERTY(int maxSteps READ maxSteps WRITE setMaxSteps NOTIFY maxStepsChanged)
    Q_PROPERTY(bool allowLogin READ allowLogin WRITE setAllowLogin NOTIFY allowLoginChanged)
    Q_PROPERTY(bool allowLaunch READ allowLaunch WRITE setAllowLaunch NOTIFY allowLaunchChanged)
    Q_PROPERTY(bool allowPayments READ allowPayments WRITE setAllowPayments NOTIFY allowPaymentsChanged)
    Q_PROPERTY(QString fidelity READ fidelity WRITE setFidelity NOTIFY fidelityChanged)
    Q_PROPERTY(bool running READ running NOTIFY runningChanged)
    Q_PROPERTY(QString statusText READ statusText NOTIFY statusTextChanged)
    Q_PROPERTY(QString previewUrl READ previewUrl NOTIFY previewUrlChanged)
    Q_PROPERTY(bool hasApiKey READ hasApiKey NOTIFY hasApiKeyChanged)
    Q_PROPERTY(QVariantMap bugDetail READ bugDetail NOTIFY bugDetailChanged)
    Q_PROPERTY(EventLog *events READ events CONSTANT)
    Q_PROPERTY(BugList *bugs READ bugs CONSTANT)

public:
    explicit RunSupervisor(QObject *parent = nullptr);
    ~RunSupervisor() override;

    QString shellPath() const { return m_shellPath; }
    QString exePath() const { return m_exePath; }
    QString task() const { return m_task; }
    QString provider() const { return m_provider; }
    QString model() const { return m_model; }
    QString baseUrl() const { return m_baseUrl; }
    int maxSteps() const { return m_maxSteps; }
    bool allowLogin() const { return m_allowLogin; }
    bool allowLaunch() const { return m_allowLaunch; }
    bool allowPayments() const { return m_allowPayments; }
    QString fidelity() const { return m_fidelity; }
    bool running() const { return m_running; }
    QString statusText() const { return m_statusText; }
    QString previewUrl() const { return m_previewUrl; }
    bool hasApiKey() const;
    QVariantMap bugDetail() const { return m_bugDetail; }
    EventLog *events() { return m_events; }
    BugList *bugs() { return m_bugs; }

    void setShellPath(const QString &value);
    void setExePath(const QString &value);
    void setTask(const QString &value);
    void setProvider(const QString &value);
    void setModel(const QString &value);
    void setBaseUrl(const QString &value);
    void setMaxSteps(int value);
    void setAllowLogin(bool value);
    void setAllowLaunch(bool value);
    void setAllowPayments(bool value);
    void setFidelity(const QString &value);

    Q_INVOKABLE void startRun(const QString &apiKey);
    Q_INVOKABLE void cancelRun();
    Q_INVOKABLE void shutdown();
    Q_INVOKABLE void selectEvent(int row);
    Q_INVOKABLE void selectBug(int row);

signals:
    void shellPathChanged();
    void exePathChanged();
    void taskChanged();
    void providerChanged();
    void modelChanged();
    void baseUrlChanged();
    void maxStepsChanged();
    void allowLoginChanged();
    void allowLaunchChanged();
    void allowPaymentsChanged();
    void fidelityChanged();
    void runningChanged();
    void statusTextChanged();
    void previewUrlChanged();
    void hasApiKeyChanged();
    void bugDetailChanged();

private:
    struct LaunchPaths {
        QString python;
        QString agentDir;
        QString projectRoot;
    };

    LaunchPaths locateAgent() const;
    bool startDaemon();
    void pollHealth();
    void postRun();
    void openEvents();
    void consumeEvents();
    void handleEvent(const QJsonObject &event);
    void reloadBugs();
    void setRunning(bool value);
    void setStatus(const QString &text);
    void setPreview(const QString &path);
    void fail(const QString &text);
    QString redactLine(const QString &line) const;
    QUrl daemonUrl(const QString &path) const;

    SecretVault m_vault;
    EventLog *m_events;
    BugList *m_bugs;
    QNetworkAccessManager m_nam;
    QProcess m_proc;
    QByteArray m_stream;
    QNetworkReply *m_eventsReply = nullptr;

    QString m_shellPath = QStringLiteral("C:/Qt/compclubshell");
    QString m_exePath;
    QString m_task;
    QString m_provider = QStringLiteral("openai");
    QString m_model = QStringLiteral("gpt-4o");
    QString m_baseUrl = QStringLiteral("https://api.openai.com/v1");
    int m_maxSteps = 25;
    bool m_allowLogin = false;
    bool m_allowLaunch = false;
    bool m_allowPayments = false;
    QString m_fidelity = QStringLiteral("vision");
    bool m_running = false;
    QString m_statusText = QStringLiteral("Демон не запущен");
    QString m_previewUrl;
    QVariantMap m_bugDetail;

    QString m_token;
    quint16 m_port = 0;
    QString m_runId;
    QString m_traceDir;
    int m_healthTries = 0;
    bool m_quitting = false;
    LaunchPaths m_paths;
};
