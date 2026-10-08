"""内置的 zsh 插件脚本，供 ``shellmate init`` 写入用户配置目录。

注意：此文件内容需与仓库根目录的 ``zsh/shellmate.zsh`` 保持一致。
"""

ZSH_PLUGIN = '''\
# 在 ~/.zshrc 中 source 本文件，将 Ctrl-G 绑定为 Shellmate 交互组件。
# 每个 shell 使用独立 ID；重复加载插件时保留当前会话的 ID。
if [[ "${SHELLMATE_SESSION_OWNER_PID:-}" != "$$" ]]; then
  typeset -g SHELLMATE_SESSION_OWNER_PID="$$"
  typeset -g SHELLMATE_SESSION_ID="zsh-$$-$RANDOM-$RANDOM"
  export SHELLMATE_SESSION_ID
fi

shellmate-widget() {
  local history_lines
  local question
  # 从配置读取历史行数；CLI 不可用时默认取最近 20 条。
  history_lines="$(command shellmate history-lines 2>/dev/null || print 20)"
  # 用 zsh 内置 fc 命令获取最近历史，通过环境变量传给 CLI。
  # 不直接写进命令行：历史可能含换行，展开到缓冲区会破坏命令结构。
  export SHELLMATE_HISTORY_TEXT="$(fc -ln -${history_lines} 2>/dev/null)"
  # 用户先在命令行输入问题，按 Ctrl-G 时读取当前行作为问题。
  question="$BUFFER"
  # 清空当前行，避免回答输出与问题混在一起。
  BUFFER=""
  CURSOR=0
  zle -I
  if [[ -n "$question" ]]; then
    command shellmate ask "$question"
  fi
  zle reset-prompt 2>/dev/null
}
zle -N shellmate-widget
bindkey '^G' shellmate-widget
'''
