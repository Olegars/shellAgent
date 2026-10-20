# Агент теста шела

Панель на Qt и локальный демон. Демон запускает `appsector0451.exe` из `C:\Qt\compclubshell`, снимает окно, читает журнал и просит модель сделать один шаг. Логин, запуск игр и оплата выключены, пока флаги в панели не включены. Выключение компьютера запрещено всегда. Агент закрывает только тот процесс шела, который запустил сам.

## Сборка панели

Из `C:\Qt\shellAgent`:

Qt 6.12 из `C:\Qt_new\6.12.0\mingw_64`. После сборки `windeployqt` копирует `Qt6Core.dll` и плагины рядом с exe.

```
cmake -S apps/shell -B build -G Ninja -DCMAKE_PREFIX_PATH=C:/Qt_new/6.12.0/mingw_64 -DCMAKE_CXX_COMPILER=C:/Qt_new/Tools/mingw1310_64/bin/g++.exe -DCMAKE_BUILD_TYPE=Release
cmake --build build
C:\Qt_new\6.12.0\mingw_64\bin\windeployqt.exe --release --qmldir apps/shell/qml build/ShellAgent.exe
```

Запуск: `build\ShellAgent.exe`

Нужен Python 3.11+ в `PATH` либо `agent\.venv\Scripts\python.exe`. Сторонние пакеты не обязательны. Если установлен `uiautomation`, клик по видимой подписи элемента сработает без координат.

Журнал прогона пишется в `traces\<id>\`: кадры, `events.jsonl`, `bugs.json`.
