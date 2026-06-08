; Inno Setup скрипт для системы видеомониторинга АЗС.
; Собирает установщик из dist\AZS-Monitoring (результат PyInstaller).
; Компиляция:  ISCC.exe packaging\installer.iss
; Результат:   installer_output\AZS-Monitoring-Setup.exe

#define MyAppName "AZS Monitoring"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "AZS"
#define MyAppExeName "AZS-Monitoring.exe"

[Setup]
; Уникальный идентификатор приложения (для обновлений/удаления)
AppId={{8F2C9A14-3B7E-4D6A-9C21-7E5B3C0A1F42}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; Скрипт лежит в packaging\, корень проекта — на уровень выше
SourceDir={#SourcePath}\..
OutputDir=installer_output
OutputBaseFilename=AZS-Monitoring-Setup
Compression=lzma2/max
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
; Установка в Program Files требует прав администратора
PrivilegesRequired=admin
WizardStyle=modern
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; Всё содержимое сборки PyInstaller
Source: "dist\AZS-Monitoring\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
