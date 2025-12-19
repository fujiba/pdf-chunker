# .envファイルがあれば読み込む
ifneq (,$(wildcard .env))
    include .env
    export
endif

.PHONY: build publish-test publish clean

build:
	uv build

# TestPyPIへのアップロード
# 環境変数 TEST_PYPI_TOKEN を使用
publish-test: build
	TWINE_USERNAME=__token__ TWINE_PASSWORD=$(TEST_PYPI_TOKEN) uv run twine upload --repository testpypi dist/*

# 本番PyPIへのアップロード
# 環境変数 PYPI_TOKEN を使用
publish: build
	TWINE_USERNAME=__token__ TWINE_PASSWORD=$(PYPI_TOKEN) uv run twine upload dist/*

clean:
	rm -rf dist/ build/ ./*.egg-info