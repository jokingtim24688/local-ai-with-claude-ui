; Ai Heaven — Windows installer (Inno Setup)
; A real setup wizard: installs the app, makes shortcuts, registers an
; uninstaller — instead of handing the user one loose .exe.
;
; Build steps (on Windows):
;   1. python build.py                 -> produces  dist\Ai Heaven.exe
;   2. install Inno Setup (https://jrsoftware.org/isdl.php)
;   3. open this file in Inno Setup and click Compile  (or: iscc installer\AiHeaven.iss)
;   -> output:  installer\Output\AiHeaven-Setup.exe   (this is what you share)

#define AppName "Ai Heaven"
#define AppVersion "0.1.0"
#define AppExe "Ai Heaven.exe"

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Ai Heaven
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}
OutputDir=Output
OutputBaseFilename=AiHeaven-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes
; per-user install needs no admin:
PrivilegesRequired=lowest

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "installollama"; Description: "Also install Ollama (required to run models)"; GroupDescription: "Dependencies:"; Check: not OllamaInstalled

[Files]
; the standalone app built by PyInstaller (one file, self-contained)
Source: "..\dist\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion
; optional: bundle a readme
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion isreadme

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
; offer to install Ollama via winget when the user ticked the task
Filename: "winget"; Parameters: "install --id Ollama.Ollama -e --accept-source-agreements --accept-package-agreements"; \
  StatusMsg: "Installing Ollama..."; Flags: runhidden; Tasks: installollama
; launch the app at the end
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[Code]
function OllamaInstalled: Boolean;
var rc: Integer;
begin
  { true if `ollama` resolves on PATH }
  Result := Exec('cmd.exe', '/C where ollama', '', SW_HIDE, ewWaitUntilTerminated, rc) and (rc = 0);
end;
