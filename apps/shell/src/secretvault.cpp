#include "secretvault.h"

#include <QDir>
#include <QFile>
#include <QStandardPaths>

#ifdef Q_OS_WIN
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <wincred.h>
#endif

namespace {
const wchar_t *kTarget = L"QtShellAgent/llm";
}

QString SecretVault::filePath() const
{
    QDir dir(QStandardPaths::writableLocation(QStandardPaths::AppDataLocation));
    dir.mkpath(QStringLiteral("."));
    return dir.filePath(QStringLiteral("llm-api-key"));
}

bool SecretVault::saveCredential(const QByteArray &key) const
{
#ifdef Q_OS_WIN
    CREDENTIALW cred{};
    cred.Type = CRED_TYPE_GENERIC;
    cred.TargetName = const_cast<LPWSTR>(kTarget);
    cred.CredentialBlobSize = static_cast<DWORD>(key.size());
    cred.CredentialBlob = reinterpret_cast<LPBYTE>(const_cast<char *>(key.constData()));
    cred.Persist = CRED_PERSIST_LOCAL_MACHINE;
    cred.UserName = const_cast<LPWSTR>(L"llm");
    return CredWriteW(&cred, 0);
#else
    Q_UNUSED(key);
    return false;
#endif
}

QByteArray SecretVault::loadCredential() const
{
#ifdef Q_OS_WIN
    PCREDENTIALW cred = nullptr;
    if (!CredReadW(kTarget, CRED_TYPE_GENERIC, 0, &cred) || !cred)
        return {};
    QByteArray key(reinterpret_cast<const char *>(cred->CredentialBlob), int(cred->CredentialBlobSize));
    CredFree(cred);
    return key;
#else
    return {};
#endif
}

bool SecretVault::saveFile(const QByteArray &key) const
{
    QFile file(filePath());
    if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate))
        return false;
    if (file.write(key) != key.size())
        return false;
    file.close();
    file.setPermissions(QFileDevice::ReadOwner | QFileDevice::WriteOwner);
    return true;
}

QByteArray SecretVault::loadFile() const
{
    QFile file(filePath());
    if (!file.open(QIODevice::ReadOnly))
        return {};
    return file.readAll();
}

bool SecretVault::save(const QByteArray &key) const
{
    if (saveCredential(key))
        return true;
    return saveFile(key);
}

QByteArray SecretVault::load() const
{
    const QByteArray cred = loadCredential();
    if (!cred.isEmpty())
        return cred;
    return loadFile();
}
