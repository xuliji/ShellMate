# 在 ~/.zshrc 中加载本文件，将 Ctrl-G 绑定为 Shellmate 交互组件。
# 用当前 shell 进程 PID（$$）作为会话 ID：每个窗口/标签页唯一，关闭后随之消失。
# 重复加载插件时保留同一会话 ID，避免会话记忆被重置。
if [[ "${SHELLMATE_SESSION_OWNER_PID:-}" != "$$" ]]; then
  typeset -g SHELLMATE_SESSION_OWNER_PID="$$"
  typeset -g SHELLMATE_SESSION_ID="zsh-$$"
  export SHELLMATE_SESSION_ID
fi

# 记录上一条命令及其退出码，供 Ctrl-G 空缓冲时自动解释失败原因。
typeset -g SHELLMATE_LAST_COMMAND=""
typeset -g SHELLMATE_LAST_EXIT=0

shellmate-preexec() {
  local cmd="$1"
  # 跳过 Shellmate 自身的调用，保留上一条真实命令供解释。
  case "$cmd" in
    shellmate\ *|command\ shellmate\ *) return ;;
  esac
  SHELLMATE_LAST_COMMAND="$cmd"
}

shellmate-precmd() {
  # precmd 在每条命令结束后、显示提示符前执行，$? 即上一条命令的退出码。
  SHELLMATE_LAST_EXIT=$?
}

autoload -Uz add-zsh-hook
add-zsh-hook preexec shellmate-preexec
add-zsh-hook precmd shellmate-precmd

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
  elif [[ -n "$SHELLMATE_LAST_COMMAND" ]]; then
    # 空缓冲：自动解释上一条命令（结合退出码定位失败原因）。
    export SHELLMATE_LAST_COMMAND SHELLMATE_LAST_EXIT
    command shellmate explain-last
  fi
  zle reset-prompt 2>/dev/null
}
zle -N shellmate-widget
bindkey '^G' shellmate-widget
