import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: window
    width: 1180
    height: 760
    visible: true
    title: "Агент теста шела"
    color: "#101218"

    header: TabBar {
        id: tabs
        background: Rectangle { color: "#171a22" }
        TabButton {
            text: "Подготовка"
            palette.buttonText: checked ? "#f3d2a4" : "#9aa0ad"
        }
        TabButton {
            text: "Лента"
            palette.buttonText: checked ? "#f3d2a4" : "#9aa0ad"
        }
        TabButton {
            text: "Баги"
            palette.buttonText: checked ? "#f3d2a4" : "#9aa0ad"
        }
    }

    StackLayout {
        anchors.fill: parent
        currentIndex: tabs.currentIndex
        SetupPage { }
        LivePage { }
        BugsPage { }
    }
}
