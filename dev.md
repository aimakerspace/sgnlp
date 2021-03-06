## Development Requirements

* Python >= 3.8

```sh
pip install -r requirements_dev.txt
```

## Run formatter

```
black <directory>

e.g.
black sgnlp/
```

## Running Unittests

Unit and integration tests scripts are all stored in the `tests` folder.

In order for unit tests in `Tests` folder to import the modules properly, please add the root of the repository to the 
Python path variable  prior to running test cases.

For Linux

```sh
export PYTHONPATH=.
```

For Windows

```sh
set PYTHONPATH=%cd%
```

Below is the example to execute all test cases in the `tests` folder, commands are executed at the root
of the repository.

Using Pytest package

```sh
# Run all
pytest tests/

# Run slow tests only
pytest -m slow tests/

# Run non-slow tests only
pytest -m 'not slow' tests/

# Run single script
pytest <path/to/script>
```

## Release guide

- Merge all changes to be released into `dev` branch
- Merge `dev` into `main`
- Update version in `setup.py` to the correct version
- Commit the change and tag it in Github
- Publish to PyPI
- Update demo_api and gitlab pipelines accordingly to deploy to production.
- Run production pipelines to build relevant demo apis.
- Continue deployment process in frontend/helm repo.

## Publishing to PyPI

- Requires `twine`

- Increment version number in `setup.py`

```sh
rm -rf build dist sgnlp.egg-info/

python setup.py sdist bdist_wheel

twine check dist/*

twine upload dist/*
```
