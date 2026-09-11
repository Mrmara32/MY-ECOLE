@echo off
REM ============================================================
REM  Construction de MY-ECOLE.exe (executable Windows autonome)
REM  A executer sur une machine Windows, dans le dossier du projet.
REM ============================================================

echo.
echo === Installation des dependances (y compris PyInstaller) ===
pip install -r requirements.txt
pip install pyinstaller

echo.
echo === Construction de l'executable (peut prendre 1 a 3 minutes) ===
pyinstaller MY-ECOLE.spec --noconfirm

echo.
if exist "dist\MY-ECOLE\MY-ECOLE.exe" (
    echo ============================================================
    echo  TERMINE AVEC SUCCES
    echo  Executable disponible dans : dist\MY-ECOLE\MY-ECOLE.exe
    echo  Copiez TOUT le dossier dist\MY-ECOLE\ sur le poste final
    echo  ^(pas seulement le .exe : les fichiers a cote sont necessaires^).
    echo ============================================================
) else (
    echo ============================================================
    echo  ECHEC — voir le message d'erreur ci-dessus.
    echo ============================================================
)
pause
