import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    RowLayout {
        anchors.fill: parent
        anchors.margins: 12
        spacing: 12

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: "#171a22"
            radius: 8

            ListView {
                id: log
                anchors.fill: parent
                anchors.margins: 8
                clip: true
                spacing: 6
                model: supervisor.events
                delegate: Rectangle {
                    required property string kind
                    required property string message
                    required property int step
                    required property int index
                    width: log.width
                    height: Math.max(28, line.implicitHeight + 10)
                    color: index === log.currentIndex ? "#2a241c" : "transparent"
                    radius: 4
                    Label {
                        id: line
                        x: 8
                        y: 5
                        width: parent.width - 16
                        wrapMode: Text.Wrap
                        text: step + "  " + kind + "  " + message
                        color: kind === "error" || kind === "bug" ? "#e07a7a" : "#e7e9ee"
                    }
                    MouseArea {
                        anchors.fill: parent
                        onClicked: {
                            log.currentIndex = index
                            supervisor.selectEvent(index)
                        }
                    }
                }
            }
        }

        Rectangle {
            Layout.preferredWidth: 460
            Layout.fillHeight: true
            color: "#171a22"
            radius: 8
            Image {
                anchors.fill: parent
                anchors.margins: 8
                fillMode: Image.PreserveAspectFit
                cache: false
                source: supervisor.previewUrl
                asynchronous: true
            }
            Label {
                anchors.centerIn: parent
                visible: supervisor.previewUrl.length === 0
                text: "Скриншот шага появится здесь"
                color: "#9aa0ad"
            }
        }
    }
}
