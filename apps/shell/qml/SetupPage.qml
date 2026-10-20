import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    id: page
    contentWidth: availableWidth
    padding: 18

    function applyProvider(name) {
        supervisor.provider = name
        if (name === "deepseek") {
            modelField.text = "deepseek-chat"
            baseField.text = "https://api.deepseek.com/v1"
        } else if (name === "ollama") {
            modelField.text = "llava"
            baseField.text = "http://127.0.0.1:11434"
        } else {
            modelField.text = "gpt-4o"
            baseField.text = "https://api.openai.com/v1"
        }
        supervisor.model = modelField.text
        supervisor.baseUrl = baseField.text
    }

    ColumnLayout {
        width: page.availableWidth
        spacing: 12

        Label {
            text: supervisor.statusText
            color: "#f3d2a4"
            wrapMode: Text.Wrap
            Layout.fillWidth: true
        }
        Label {
            text: supervisor.hasApiKey ? "Ключ API сохранён локально" : "Ключ API ещё не сохранён"
            color: "#9aa0ad"
        }
        Label {
            text: "На время прогона шелл откроется на весь экран. Агент закроет только тот процесс, который сам запустил."
            color: "#9aa0ad"
            wrapMode: Text.Wrap
            Layout.fillWidth: true
        }

        GridLayout {
            columns: 2
            columnSpacing: 12
            rowSpacing: 10
            Layout.fillWidth: true

            Label { text: "Каталог шела"; color: "#c6cad3" }
            TextField {
                id: shellField
                Layout.fillWidth: true
                text: "C:/Qt/compclubshell"
                color: "#e7e9ee"
                background: Rectangle { color: "#1a1d27"; radius: 6; border.color: "#2c3140" }
            }

            Label { text: "Exe шела"; color: "#c6cad3" }
            TextField {
                id: exeField
                Layout.fillWidth: true
                placeholderText: "пусто — искать appsector0451.exe в build"
                color: "#e7e9ee"
                background: Rectangle { color: "#1a1d27"; radius: 6; border.color: "#2c3140" }
            }

            Label { text: "Провайдер"; color: "#c6cad3" }
            ComboBox {
                id: providerBox
                model: ["openai", "deepseek", "ollama"]
                Layout.fillWidth: true
                onActivated: page.applyProvider(currentText)
            }

            Label { text: "Модель"; color: "#c6cad3" }
            TextField {
                id: modelField
                Layout.fillWidth: true
                text: "gpt-4o"
                color: "#e7e9ee"
                background: Rectangle { color: "#1a1d27"; radius: 6; border.color: "#2c3140" }
            }

            Label { text: "Base URL"; color: "#c6cad3" }
            TextField {
                id: baseField
                Layout.fillWidth: true
                text: "https://api.openai.com/v1"
                color: "#e7e9ee"
                background: Rectangle { color: "#1a1d27"; radius: 6; border.color: "#2c3140" }
            }

            Label { text: "Ключ API"; color: "#c6cad3" }
            TextField {
                id: keyField
                Layout.fillWidth: true
                echoMode: TextInput.Password
                placeholderText: "не попадает в журнал. Для Ollama можно пустым"
                color: "#e7e9ee"
                background: Rectangle { color: "#1a1d27"; radius: 6; border.color: "#2c3140" }
            }

            Label { text: "Лимит шагов"; color: "#c6cad3" }
            SpinBox {
                id: stepsBox
                from: 5
                to: 40
                value: 25
                editable: true
            }

            Label { text: "Режим"; color: "#c6cad3" }
            ComboBox {
                id: fidelityBox
                model: ["vision", "log-only"]
                Layout.fillWidth: true
            }
        }

        RowLayout {
            CheckBox { id: loginBox; text: "Разрешить логин"; palette.windowText: "#e7e9ee" }
            CheckBox { id: launchBox; text: "Разрешить запуск игр"; palette.windowText: "#e7e9ee" }
            CheckBox { id: payBox; text: "Разрешить оплату"; palette.windowText: "#e7e9ee" }
        }

        Label { text: "Сценарий"; color: "#c6cad3" }
        TextArea {
            id: taskField
            Layout.fillWidth: true
            Layout.preferredHeight: 110
            wrapMode: TextEdit.Wrap
            text: "Проверь экран гостя: видны название клуба, имя ПК и вход. Ошибок QML быть не должно. Игры, оплату и выключение не трогай."
            color: "#e7e9ee"
            background: Rectangle { color: "#1a1d27"; radius: 6; border.color: "#2c3140" }
        }

        RowLayout {
            Button {
                text: "Запустить"
                enabled: !supervisor.running
                onClicked: {
                    supervisor.shellPath = shellField.text.trim()
                    supervisor.exePath = exeField.text.trim()
                    supervisor.provider = providerBox.currentText
                    supervisor.model = modelField.text.trim()
                    supervisor.baseUrl = baseField.text.trim()
                    supervisor.maxSteps = stepsBox.value
                    supervisor.fidelity = fidelityBox.currentText
                    supervisor.allowLogin = loginBox.checked
                    supervisor.allowLaunch = launchBox.checked
                    supervisor.allowPayments = payBox.checked
                    supervisor.task = taskField.text.trim()
                    var typedKey = keyField.text
                    keyField.text = ""
                    supervisor.startRun(typedKey)
                }
            }
            Button {
                text: "Отменить"
                enabled: supervisor.running
                onClicked: supervisor.cancelRun()
            }
        }
    }
}
