cmake_minimum_required(VERSION 3.21)

project(ShellAgent VERSION 0.1 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(Qt6 REQUIRED COMPONENTS Quick QuickControls2 Network)

qt_standard_project_setup()

qt_add_executable(ShellAgent WIN32
    main.cpp
    src/secretvault.h
    src/secretvault.cpp
    src/runsupervisor.h
    src/runsupervisor.cpp
)

target_include_directories(ShellAgent PRIVATE src)

qt_add_qml_module(ShellAgent
    URI ShellAgent
    VERSION 1.0
    QML_FILES
        qml/Main.qml
        qml/SetupPage.qml
        qml/LivePage.qml
        qml/BugsPage.qml
)

target_link_libraries(ShellAgent PRIVATE Qt6::Quick Qt6::QuickControls2 Qt6::Network)

if (WIN32)
    target_link_libraries(ShellAgent PRIVATE advapi32)
endif()

if (MSVC)
    target_compile_options(ShellAgent PRIVATE /utf-8)
endif()
