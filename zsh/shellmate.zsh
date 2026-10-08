# 在 ~/.zshrc 中加载本文件，将 Ctrl-G 绑定为 Shellmate 交互组件。
# 每个 shell 使用独立 ID；重复加载插件时保留当前会话的 ID。
if [[ "${SHELLMATE_SESSION_OWNER_PID:-}" != "$$" ]]; then
  typeset -g SHELLMATE_SESSION_OWNER_PID="$$"
  typeset -g SHELLMATE_SESSION_ID="zsh-$$-$RANDOM-$RANDOM"
  export SHELLMATE_SESSION_ID
fi

shellmate-widget() {
  local history_text
  local history_lines
  # 从配置读取历史行数；CLI 不可用时默认取最近 20 条。
  history_lines="$(command shellmate history-lines 2>/dev/null || print 20)"
  # 使用 zsh 内置 fc 命令获取最近历史，并传给 Python CLI。
  history_text="$(fc -ln -${history_lines} 2>/dev/null)"
  # 退出 ZLE 行编辑状态后运行 CLI，完成后刷新提示符。
  zle -I
  command shellmate ask --history "$history_text" --thread-id "$SHELLMATE_SESSION_ID"
  zle reset-prompt 2>/dev/null
}
zle -N shellmate-widget
bindkey '^G' shellmate-widget
