pip install --upgrade pip wheel
pip install -r requirements.txt
pip install -r requirements-libs.txt --target ./addon/globalPlugins/CaptionLocal/libs --platform win_amd64 --only-binary=:all: --no-binary=:none: --upgrade
pip install miniqinference[cli] --target ./addon/globalPlugins/CaptionLocal/libs --upgrade

set SKIP="no-commit-to-branch"
pre-commit run --all

scons