#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQmlContext>

#include "src/runsupervisor.h"

int main(int argc, char *argv[])
{
    qputenv("QT_QUICK_CONTROLS_STYLE", "Basic");
    QGuiApplication app(argc, argv);
    QCoreApplication::setOrganizationName(QStringLiteral("ShellAgent"));
    QCoreApplication::setApplicationName(QStringLiteral("ShellTester"));

    RunSupervisor supervisor;
    QQmlApplicationEngine engine;
    engine.rootContext()->setContextProperty(QStringLiteral("supervisor"), &supervisor);
    QObject::connect(&app, &QGuiApplication::aboutToQuit, &supervisor, &RunSupervisor::shutdown);
    engine.loadFromModule("ShellAgent", "Main");
    if (engine.rootObjects().isEmpty())
        return 1;
    return app.exec();
}
