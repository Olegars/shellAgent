#pragma once

#include <QByteArray>

class SecretVault
{
public:
    bool save(const QByteArray &key) const;
    QByteArray load() const;

private:
    bool saveCredential(const QByteArray &key) const;
    QByteArray loadCredential() const;
    bool saveFile(const QByteArray &key) const;
    QByteArray loadFile() const;
    QString filePath() const;
};
