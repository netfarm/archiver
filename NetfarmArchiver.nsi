; Netfarm Mail Archiver - release 2
;
; Copyright (C) 2005-2007 Gianluigi Tiesi <sherpya@netfarm.it>
; Copyright (C) 2005-2007 NetFarm S.r.l.  [http://www.netfarm.it]
;
; This program is free software; you can redistribute it and/or modify
; it under the terms of the GNU General Public License as published by the
; Free Software Foundation; either version 2, or (at your option) any later
; version.
;
; This program is distributed in the hope that it will be useful, but
; WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTIBILITY
; or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License
; for more details.

; Include Modern UI
!include "MUI.nsh"

; Compression
SetCompressor lzma

; General
Name "Netfarm Mail Archiver"
OutFile "NetfarmMailArchiver.exe"

Icon "nma.ico"
InstallDir "$PROGRAMFILES\NMA"
InstallDirRegKey HKLM "Software\Netfarm\Netfarm Mail Archiver" "InstallPath"

SetCompress auto
!packhdr tmp.dat "upx --best tmp.dat"
SetDateSave on
SetDatablockOptimize on
CRCCheck on
SilentInstall normal
InstallColors FF8080 000030
WindowIcon on
XPStyle on

;--------------------------------
; Variables

Var MUI_TEMP
Var STARTMENU_FOLDER

;--------------------------------
; Interface Settings

!define MUI_ABORTWARNING

;--------------------------------
; Pages

!insertmacro MUI_PAGE_LICENSE "copyright.txt"
!insertmacro MUI_PAGE_DIRECTORY
  
; Start Menu Folder Page Configuration
!define MUI_STARTMENUPAGE_REGISTRY_ROOT "HKLM" 
!define MUI_STARTMENUPAGE_REGISTRY_KEY "Software\Netfarm\Netfarm Mail Archiver" 
!define MUI_STARTMENUPAGE_REGISTRY_VALUENAME "Start Menu Folder"
  
!insertmacro MUI_PAGE_STARTMENU Application $STARTMENU_FOLDER
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

;--------------------------------
; Languages
 
!insertmacro MUI_LANGUAGE "Italian"
!insertmacro MUI_LANGUAGE "English"

; Setup Versioning
VIProductVersion "2.0.0.0"
VIAddVersionKey /LANG=${LANG_ENGLISH} "ProductName" "Netfarm Mail Archiver"
VIAddVersionKey /LANG=${LANG_ENGLISH} "Comments" "Netfarm Mail Archiver"
VIAddVersionKey /LANG=${LANG_ENGLISH} "CompanyName" "Netfarm"
VIAddVersionKey /LANG=${LANG_ENGLISH} "LegalCopyright" "© 2005 Gianluigi Tiesi"
VIAddVersionKey /LANG=${LANG_ENGLISH} "FileDescription" "Netfarm Mail Archiver"
VIAddVersionKey /LANG=${LANG_ENGLISH} "FileVersion" "2.0.0"

;--------------------------------
; Installer Sections
Section
  SetOutPath "$INSTDIR"   
  File "dist\*.*"
  File /oname=archiver.ini archiver-win32.ini
  File /oname=NMA-epydoc.pdf api\api.pdf
  
  ; Store installation folder
  WriteRegStr HKLM "Software\Netfarm\Netfarm Mail Archiver" "ConfigFile" $INSTDIR\archiver.ini
  WriteRegStr HKLM "Software\Netfarm\Netfarm Mail Archiver" "InstallPath" $INSTDIR
  
  ; Update ini file
  WriteINIStr $INSTDIR\archiver.ini global logfile $INSTDIR\archiver.log

  WriteINIStr $INSTDIR\archiver.ini archive hashdb $INSTDIR\archive.db
  
  CreateDirectory "$INSTDIR\Storage"
  WriteINIStr $INSTDIR\archiver.ini storage storagedir $INSTDIR\Storage
  WriteINIStr $INSTDIR\archiver.ini storage hashdb $INSTDIR\storage.db
  
  FlushINI $INSTDIR\archiver.ini
  
  ; Create uninstaller
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  
  !insertmacro MUI_STARTMENU_WRITE_BEGIN Application

  ; TODO check if installed on nt/2k/xp/2k3
  ExecWait '"$INSTDIR\archiver_svc.exe" -remove'
  ExecWait '"$INSTDIR\archiver_svc.exe" -install'
  
  ;Create shortcuts
  CreateDirectory "$SMPROGRAMS\$STARTMENU_FOLDER"
  CreateShortCut "$SMPROGRAMS\$STARTMENU_FOLDER\Netfarm Mail Archiver - Console.lnk" "$INSTDIR\archiver.exe" -d
  CreateShortCut "$SMPROGRAMS\$STARTMENU_FOLDER\Netfarm Mail Archiver - Epydoc.lnk" "$INSTDIR\NMA-epydoc.pdf"
  CreateShortCut "$SMPROGRAMS\$STARTMENU_FOLDER\Uninstall.lnk" "$INSTDIR\Uninstall.exe"
  !insertmacro MUI_STARTMENU_WRITE_END
SectionEnd


;--------------------------------
; Uninstaller Section

Section "Uninstall"

  ExecWait '"$INSTDIR\archiver_svc.exe" -remove'
  ; TODO launch a messagebox saying/asking to remove storage/etc
  RMDir /r "$INSTDIR"
  
  !insertmacro MUI_STARTMENU_GETFOLDER Application $MUI_TEMP

  Delete "$SMPROGRAMS\$MUI_TEMP\Netfarm Mail Archiver - Console.lnk"
  Delete "$SMPROGRAMS\$MUI_TEMP\Netfarm Mail Archiver - Doxygen.lnk"
  Delete "$SMPROGRAMS\$MUI_TEMP\Netfarm Mail Archiver - Epydoc.lnk"
  Delete "$SMPROGRAMS\$MUI_TEMP\Uninstall.lnk"
  
  ; Delete empty start menu parent diretories
  StrCpy $MUI_TEMP "$SMPROGRAMS\$MUI_TEMP"
 
  startMenuDeleteLoop:
    RMDir $MUI_TEMP
    GetFullPathName $MUI_TEMP "$MUI_TEMP\.."
    
    IfErrors startMenuDeleteLoopDone
  
    StrCmp $MUI_TEMP $SMPROGRAMS startMenuDeleteLoopDone startMenuDeleteLoop
  startMenuDeleteLoopDone:

  DeleteRegKey HKLM "Software\Netfarm\Netfarm Mail Archiver"
  DeleteRegKey /ifempty HKLM "Software\Netfarm"

SectionEnd
