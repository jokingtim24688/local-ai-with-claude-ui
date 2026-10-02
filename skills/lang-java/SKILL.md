---
name: lang-java
description: Java apps — javac/Maven/Gradle, project layout, and Swing / JavaFX menu bars.
domain: java
triggers: java, javac, jar, maven, pom.xml, gradle, gradlew, build.gradle, swing, javafx, jframe, spring, minecraft, minecraft mod, mod, mods, modding, forge, fabric, mixin, android, .java, jvm, compile
---
# Java skill

RUN / CHECK
```
javac -d out src/**/*.java        # compile (this IS the syntax check)
java -cp out com.example.Main     # run
mvn -q compile | mvn -q package   # Maven project
gradle build | ./gradlew build    # Gradle project
```
Always compile with `javac` before claiming it works.

LAYOUT — the folder path MUST match the package
```
src/main/java/com/example/Main.java   ->  package com.example;
pom.xml  or  build.gradle
```
`public class Main` must live in `Main.java`. One public class per file, same name.

MENU BAR — Swing (in the JDK, nothing to install)
```java
package com.example;

import javax.swing.*;
import java.awt.*;
import java.awt.event.KeyEvent;
import java.io.File;
import java.nio.file.Files;

public class Main extends JFrame {
    private final JTextArea text = new JTextArea();

    public Main() {
        super("My App");
        setDefaultCloseOperation(EXIT_ON_CLOSE);
        setSize(900, 600);
        add(new JScrollPane(text), BorderLayout.CENTER);
        setJMenuBar(buildMenu());                 // REQUIRED: setJMenuBar, not add()
    }

    private JMenuBar buildMenu() {
        JMenuBar bar = new JMenuBar();
        JMenu file = new JMenu("File");
        file.setMnemonic(KeyEvent.VK_F);          // Alt+F
        JMenuItem open = new JMenuItem("Open...");
        open.setAccelerator(KeyStroke.getKeyStroke("control O"));
        open.addActionListener(e -> openFile());
        file.add(open);
        file.addSeparator();
        JMenuItem quit = new JMenuItem("Quit");
        quit.addActionListener(e -> dispose());
        file.add(quit);
        bar.add(file);
        JMenu help = new JMenu("Help");
        JMenuItem about = new JMenuItem("About");
        about.addActionListener(e -> JOptionPane.showMessageDialog(this, "My App 1.0"));
        help.add(about);
        bar.add(help);
        return bar;
    }

    private void openFile() {
        JFileChooser c = new JFileChooser();
        if (c.showOpenDialog(this) == JFileChooser.APPROVE_OPTION) {
            try {
                File f = c.getSelectedFile();
                text.setText(Files.readString(f.toPath()));
            } catch (Exception ex) {
                JOptionPane.showMessageDialog(this, "Could not read: " + ex.getMessage());
            }
        }
    }

    public static void main(String[] args) {
        SwingUtilities.invokeLater(() -> new Main().setVisible(true));  // Swing is NOT thread-safe
    }
}
```

MENU BAR — JavaFX (needs the JavaFX SDK on the module path)
```java
MenuBar bar = new MenuBar();
Menu file = new Menu("File");
MenuItem open = new MenuItem("Open...");
open.setAccelerator(KeyCombination.keyCombination("Ctrl+O"));
open.setOnAction(e -> openFile());
file.getItems().addAll(open, new SeparatorMenuItem(), new MenuItem("Quit"));
bar.getMenus().add(file);
root.setTop(bar);                                 // BorderPane
```

TRAPS
- Build UI on the Event Dispatch Thread: `SwingUtilities.invokeLater(...)`.
- `setJMenuBar(bar)` — using `add(bar)` puts the menu in the layout and looks broken.
- Checked exceptions must be caught or declared; file I/O throws `IOException`.
- `==` compares references for objects; use `.equals()` for String content.
- `Files.readString` needs Java 11+; on Java 8 use `new String(Files.readAllBytes(p))`.
