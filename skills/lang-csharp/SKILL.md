---
name: lang-csharp
description: C# / .NET apps — dotnet CLI, WinForms and WPF menus, and Unity C# scripts.
domain: csharp
triggers: c#, csharp, dotnet, .net, winforms, wpf, maui, xaml, unity, monobehaviour, visual studio, nuget, .cs, blazor, asp.net
---
# C# / .NET skill

RUN / CHECK
```
dotnet new winforms -o MyApp     # or: console, wpf, maui, classlib
dotnet build                     # this IS the syntax check
dotnet run --project MyApp
dotnet add package <name>        # NuGet
```
WinForms and WPF are Windows-only. A console app runs anywhere.

MENU — WinForms (`MyApp.csproj` needs `<UseWindowsForms>true</UseWindowsForms>`)
```csharp
using System;
using System.IO;
using System.Windows.Forms;

public class MainForm : Form
{
    private readonly TextBox _text = new() { Multiline = true, Dock = DockStyle.Fill, ScrollBars = ScrollBars.Both };

    public MainForm()
    {
        Text = "My App";
        Width = 900; Height = 600;

        var open = new ToolStripMenuItem("&Open...") { ShortcutKeys = Keys.Control | Keys.O };
        open.Click += (s, e) => OpenFile();
        var quit = new ToolStripMenuItem("&Quit", null, (s, e) => Close());
        var file = new ToolStripMenuItem("&File");
        file.DropDownItems.AddRange(new ToolStripItem[] { open, new ToolStripSeparator(), quit });

        var menu = new MenuStrip();
        menu.Items.Add(file);
        Controls.Add(_text);          // add the fill control FIRST
        Controls.Add(menu);           // then the menu, so Dock.Top wins
        MainMenuStrip = menu;
    }

    private void OpenFile()
    {
        using var d = new OpenFileDialog();
        if (d.ShowDialog() == DialogResult.OK) _text.Text = File.ReadAllText(d.FileName);
    }

    [STAThread]                       // REQUIRED for WinForms dialogs
    public static void Main() => Application.Run(new MainForm());
}
```

MENU — WPF (XAML)
```xml
<Window x:Class="MyApp.MainWindow" xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml" Title="My App" Height="600" Width="900">
  <DockPanel>
    <Menu DockPanel.Dock="Top">
      <MenuItem Header="_File">
        <MenuItem Header="_Open..." Click="Open_Click" InputGestureText="Ctrl+O"/>
        <Separator/>
        <MenuItem Header="_Quit" Click="Quit_Click"/>
      </MenuItem>
    </Menu>
    <TextBox x:Name="Body" AcceptsReturn="True" VerticalScrollBarVisibility="Auto"/>
  </DockPanel>
</Window>
```

UNITY C# — one class per file, the file name MUST equal the class name
```csharp
using UnityEngine;

public class PlayerMover : MonoBehaviour      // file: PlayerMover.cs
{
    [SerializeField] private float speed = 5f;   // shows in the Inspector

    private void Update()                        // every frame
    {
        float h = Input.GetAxis("Horizontal");
        transform.Translate(Vector3.right * h * speed * Time.deltaTime);  // ALWAYS * Time.deltaTime
    }
}
```

TRAPS
- WinForms needs `[STAThread]` on Main or dialogs crash.
- Add the docked-fill control before the MenuStrip, or the menu covers it.
- Unity: file name must match the class name exactly, or the component will not attach.
- Unity: multiply movement by `Time.deltaTime` or speed depends on the frame rate.
- `using var` needs C# 8+; `dotnet build` tells you if the language version is too old.
