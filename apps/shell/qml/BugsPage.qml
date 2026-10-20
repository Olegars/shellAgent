import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    RowLayout {
        anchors.fill: parent
        anchors.margins: 12
        spacing: 12

        Rectangle {
            Layout.preferredWidth: 360
            Layout.fillHeight: true
            color: "#171a22"
            radius: 8
            ListView {
                id: bugList
                anchors.fill: parent
                anchors.margins: 8
                clip: true
                spacing: 6
                model: supervisor.bugs
                delegate: Rectangle {
                    required property string title
                    required property string severity
                    required property int index
                    width: bugList.width
                    height: textItem.implicitHeight + 16
                    radius: 4
                    color: severity === "blocker" ? "#3a2224" : severity === "major" ? "#3a3220" : "#243028"
                    Label {
                        id: textItem
                        x: 8
                        y: 8
                        width: parent.width - 16
                        wrapMode: Text.Wrap
                        text: severity + "  " + title
                        color: "#e7e9ee"
                    }
                    MouseArea {
                        anchors.fill: parent
                        onClicked: supervisor.selectBug(index)
                    }
                }
            }
            Label {
                anchors.centerIn: parent
                visible: bugList.count === 0
                text: "Расхождений пока нет"
                color: "#9aa0ad"
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: "#171a22"
            radius: 8
            ScrollView {
                id: bugScroll
                anchors.fill: parent
                anchors.margins: 12
                contentWidth: availableWidth
                ColumnLayout {
                    width: bugScroll.availableWidth
                    spacing: 8
                    Label {
                        text: supervisor.bugDetail.title || "Выберите баг"
                        color: "#f3d2a4"
                        wrapMode: Text.Wrap
                        Layout.fillWidth: true
                        font.pixelSize: 18
                    }
                    Label {
                        visible: (supervisor.bugDetail.severity || "").length > 0
                        text: (supervisor.bugDetail.severity || "")
                             + (supervisor.bugDetail.requestUrl ? "  " + supervisor.bugDetail.requestUrl : "")
                        color: "#e7e9ee"
                        wrapMode: Text.Wrap
                        Layout.fillWidth: true
                    }
                    Label {
                        text: "Ожидание: " + (supervisor.bugDetail.expected || "")
                        color: "#9aa0ad"
                        wrapMode: Text.Wrap
                        Layout.fillWidth: true
                    }
                    Label {
                        text: "Факт: " + (supervisor.bugDetail.actual || "")
                        color: "#9aa0ad"
                        wrapMode: Text.Wrap
                        Layout.fillWidth: true
                    }
                    Label { text: "Шаги воспроизведения"; color: "#c6cad3" }
                    Repeater {
                        model: supervisor.bugDetail.steps || []
                        Label {
                            required property string modelData
                            required property int index
                            text: (index + 1) + ". " + modelData
                            color: "#e7e9ee"
                            wrapMode: Text.Wrap
                            Layout.fillWidth: true
                        }
                    }
                    Image {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 280
                        fillMode: Image.PreserveAspectFit
                        cache: false
                        source: supervisor.bugDetail.shotUrl || ""
                    }
                }
            }
        }
    }
}
