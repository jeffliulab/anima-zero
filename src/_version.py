"""Single source of truth for the version number.

Kept in its own module with nothing but a literal so that build backends can read it
statically, without importing ``anima`` (which would pull in anthropic/openai/fastapi
at build time). ``pyproject.toml`` reads it via ``attr: anima._version.__version__``.

Three things must agree, and CI enforces it on every tag push:
``git tag`` == ``__version__`` == the top entry of ``CHANGELOG.md``.

版本号的单一来源。

单独一个模块、里面只有一个字面量，好让构建后端**静态**读到它，而不必 import ``anima``
（那会在构建期把 anthropic/openai/fastapi 全拖进来）。``pyproject.toml`` 经
``attr: anima._version.__version__`` 读这里。

三处必须一致，CI 在每次推 tag 时强制校验：``git tag`` == ``__version__`` == ``CHANGELOG.md`` 顶栏。
"""

__version__ = "1.0.1"
