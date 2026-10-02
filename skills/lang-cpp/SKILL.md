---
name: lang-cpp
description: C and C++ — compiling with g++/CMake, project layout, and Qt / Win32 menu bars.
domain: cpp
triggers: c++, cpp, c language, gcc, g++, clang, cmake, makefile, header, .cpp, .h, .hpp, qt, win32, sdl, opengl, unreal c++, pointer, segfault, stl, vector
---
# C / C++ skill

BUILD / CHECK — compiling IS the syntax check, always do it
```
g++ -std=c++17 -Wall -Wextra -o app main.cpp     # C++
gcc  -std=c11  -Wall -Wextra -o app main.c       # C
./app
```
CMake for anything with more than one file:
```cmake
cmake_minimum_required(VERSION 3.16)
project(MyApp CXX)
set(CMAKE_CXX_STANDARD 17)
add_executable(MyApp src/main.cpp src/ui.cpp)
```
```
cmake -B build && cmake --build build
```

LAYOUT
```
src/main.cpp  src/ui.cpp  include/ui.h  CMakeLists.txt
```
Every header starts with `#pragma once` (or include guards) or you get duplicate-symbol errors.

MENU BAR — Qt 6 (`find_package(Qt6 COMPONENTS Widgets REQUIRED)`)
```cpp
#include <QApplication>
#include <QMainWindow>
#include <QMenuBar>
#include <QTextEdit>
#include <QFileDialog>
#include <QFile>
#include <QTextStream>

class Win : public QMainWindow {
public:
    Win() {
        edit = new QTextEdit(this);
        setCentralWidget(edit);
        QMenu *file = menuBar()->addMenu("&File");          // & = Alt shortcut
        QAction *open = file->addAction("&Open...");
        open->setShortcut(QKeySequence::Open);
        connect(open, &QAction::triggered, this, &Win::openFile);
        file->addSeparator();
        QAction *quit = file->addAction("&Quit");
        connect(quit, &QAction::triggered, this, &QWidget::close);
    }
private:
    QTextEdit *edit;
    void openFile() {
        QString p = QFileDialog::getOpenFileName(this);
        if (p.isEmpty()) return;
        QFile f(p);
        if (f.open(QIODevice::ReadOnly | QIODevice::Text))
            edit->setPlainText(QTextStream(&f).readAll());
    }
};

int main(int argc, char **argv) {
    QApplication app(argc, argv);
    Win w; w.resize(900, 600); w.show();
    return app.exec();
}
```
A class with its own signals/slots needs the `Q_OBJECT` macro and `set(CMAKE_AUTOMOC ON)`.

MENU — plain Win32 (no framework)
```cpp
HMENU bar = CreateMenu(), file = CreatePopupMenu();
AppendMenu(file, MF_STRING, 1001, L"&Open\tCtrl+O");
AppendMenu(file, MF_SEPARATOR, 0, nullptr);
AppendMenu(file, MF_STRING, 1002, L"&Quit");
AppendMenu(bar, MF_POPUP, (UINT_PTR)file, L"&File");
SetMenu(hwnd, bar);
// handle WM_COMMAND: LOWORD(wParam) is 1001 / 1002
```

UNREAL C++ — classes get a prefix and a macro, and the build file lists modules
```cpp
UCLASS()                       // A = Actor, U = UObject, F = plain struct
class MYGAME_API AMyActor : public AActor {
    GENERATED_BODY()           // REQUIRED, right after the opening brace
public:
    UPROPERTY(EditAnywhere, Category="Setup") float Speed = 100.f;
    virtual void Tick(float DeltaTime) override;
};
```
Regenerate project files after adding a class, and rebuild from the editor or your IDE.

TRAPS
- Every `new` needs a `delete`; prefer `std::unique_ptr` / `std::vector` and avoid raw owning pointers.
- Returning a pointer or reference to a local variable is a dangling pointer (crash later, not now).
- C has no `bool` before C99 (`#include <stdbool.h>`) and no classes — do not mix C++ syntax into a `.c` file.
- Fix every `-Wall -Wextra` warning; most are real bugs.
- Qt: a widget with a parent is deleted by the parent — do not `delete` it yourself.
