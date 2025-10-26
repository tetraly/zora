#cs ----------------------------------------------------------------------------

	 AutoIt Version: 3.3.18.0
	 Author:         myName

	 Script Function:
		Template AutoIt script.

#ce ----------------------------------------------------------------------------

; Script Start - Add your code below here

#include <GuiComboBox.au3>
Opt("WinTitleMatchMode", 2) ; substring match

; ================================
; CONFIGURABLE VARIABLES
; ================================
Local $expectedVersion = "3.5.22"
Local $tempFileName    = "ZeldaMessage.tmp"
Local $controlROM      = "[NAME:fileName]"            ; Base ROM input field
Local $controlFlags    = "[NAME:flagNumber]"          ; Flags input field
Local $controlSeed     = "[NAME:seed]"                ; Seed input field
Local $controlGenerate = "[NAME:generateButton]"      ; Generate button
Local $saveDialogTitle = "[TITLE:Zelda Randomizer " & $expectedVersion & "; CLASS:#32770]" ; Confirmation dialog
Local $waitDialogSec   = 5                     ; Seconds to wait for confirmation dialog

; ================================
; FIND ZELDA RANDOMIZER WINDOW
; ================================
Local $randoWindow = WinGetHandle("Zelda Randomizer " & $expectedVersion)
If $randoWindow = 0 Then
    MsgBox(16, "Error", "Cannot find Zelda Randomizer " & $expectedVersion & " app. Please open it and try again.")
    Exit
EndIf

; ================================
; VERSION CHECK
; ================================
Local $title = WinGetTitle($randoWindow)
Local $version = ""
If StringRegExp($title, "Zelda Randomizer\s+([0-9]+\.[0-9]+\.[0-9]+)", 0) Then
    $version = StringRegExpReplace($title, ".*Zelda Randomizer\s+([0-9]+\.[0-9]+\.[0-9]+).*", "\1")
EndIf

If $version <> $expectedVersion And $version <> "" Then
    Local $choice = MsgBox(49, "Version Mismatch", _
        "Expected version " & $expectedVersion & ", detected " & $version & "." & @LF & _
        "Continue anyway?" & @LF & "Yes=Continue, No=Abort")
    If $choice = 7 Then Exit
EndIf

; Bring window to front
WinActivate($randoWindow)
Sleep(100)

; ================================
; READ TEMP FILE
; ================================
Local $file = FileOpen(@TempDir & "\" & $tempFileName)
If $file = -1 Then
    MsgBox(16, "Failure", "Error reading temp file")
    Exit
EndIf

Local $rom   = FileReadLine($file) ; Base ROM path
Local $flags = FileReadLine($file) ; Flags
Local $seed  = FileReadLine($file) ; Seed
FileClose($file)

; ================================
; FILL OUT RANDOMIZER FORM
; ================================
ControlSetText($randoWindow, "", $controlROM, $rom)
ControlSetText($randoWindow, "", $controlFlags, $flags)
ControlSetText($randoWindow, "", $controlSeed, $seed)

; ================================
; CLICK GENERATE
; ================================
ControlClick($randoWindow, "", $controlGenerate)
Sleep(500) ; allow dialog to appear

; ================================
; WAIT FOR CONFIRMATION DIALOG
; ================================
Local $dialogBox = WinWait($saveDialogTitle, "", $waitDialogSec)
If $dialogBox <> 0 Then
    WinClose($randoWindow)
EndIf

