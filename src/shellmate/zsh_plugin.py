"""内置的 zsh 插件脚本，供 ``shellmate-ai init`` 写入用户配置目录。

插件内容以包内数据文件 ``shellmate.zsh`` 作为唯一来源，运行时通过
``importlib.resources`` 读取，避免与仓库中的 zsh 插件维护两份重复代码。
"""

from importlib.resources import files

ZSH_PLUGIN = files("shellmate").joinpath("shellmate.zsh").read_text(encoding="utf-8")
