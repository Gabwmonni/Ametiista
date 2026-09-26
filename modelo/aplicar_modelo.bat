@echo off
chcp 65001 >nul
cd /d "%~dp0\.."
rem Depois de editar a Ametista no Blender e exportar como modelo\exportado.glb (veja modelo\LEIA-ME-MODELO.md):
rem deixa o modelo leve e coloca no app (PC e celular).
if not exist "modelo\exportado.glb" (
  echo Exporte do Blender como modelo\exportado.glb primeiro. O passo a passo esta em modelo\LEIA-ME-MODELO.md.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
python modelo\compactar_glb.py modelo\exportado.glb web\ametista.glb || (pause & exit /b 1)
copy /y web\ametista.glb celular\public\ametista.glb >nul
echo.
echo  Pronto! Feche e abra a Ametista para ver o modelo novo na barra.
echo  Para o celular: publicar_celular.bat
pause
