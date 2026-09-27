@echo off
REM Disparado pelo Agendador de Tarefas do Windows, aos sábados.
REM O log de cada execução fica em publicacao.log, ao lado deste arquivo.
cd /d "%~dp0"
REM O interpretador e o do venv do projeto. O caminho anterior era o atalho do
REM Python da Microsoft Store, que desapareceu em 27/09/2026 levando consigo os
REM pacotes da coleta.
if not exist ".venv\Scripts\python.exe" (
  echo %DATE% %TIME%  venv ausente: reconstrua com o Python de Programs >> publicacao.log
  exit /b 1
)
".venv\Scripts\python.exe" publicar_automatico.py >> publicacao_saida.log 2>&1
