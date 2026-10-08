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
# 标记上一条命令是否为 Shellmate 自身调用，避免对自身失败误报提示。
typeset -g SHELLMATE_INTERNAL_COMMAND=0

shellmate-preexec() {
  local cmd="$1"
  # 跳过 Shellmate 自身的调用，保留上一条真实命令供解释。
  case "$cmd" in
    shellmate-ai\ *|command\ shellmate-ai\ *)
      SHELLMATE_INTERNAL_COMMAND=1
      return ;;
  esac
  SHELLMATE_INTERNAL_COMMAND=0
  SHELLMATE_LAST_COMMAND="$cmd"
}

shellmate-precmd() {
  # precmd 在每条命令结束后、显示提示符前执行，$? 即上一条命令的退出码。
  SHELLMATE_LAST_EXIT=$?
  # 真实命令失败时，在提示符上方提示可重跑并让 agent 看完整报错。
  if [[ $SHELLMATE_INTERNAL_COMMAND -eq 0 && $SHELLMATE_LAST_EXIT -ne 0 && -n "$SHELLMATE_LAST_COMMAND" ]]; then
    print -P "%F{yellow}⚠ 上一条命令失败 (exit $SHELLMATE_LAST_EXIT)%f"
    print -P "%F{yellow}  按 Ctrl-X 重跑并用报错让 agent 解释，或按 Ctrl-G 直接解释%f"
  fi
  SHELLMATE_INTERNAL_COMMAND=0
}

autoload -Uz add-zsh-hook
add-zsh-hook preexec shellmate-preexec
add-zsh-hook precmd shellmate-precmd

shellmate-widget() {
  local history_lines
  local question
  # 从配置读取历史行数；CLI 不可用时默认取最近 20 条。
  history_lines="$(command shellmate-ai history-lines 2>/dev/null || print 20)"
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
    command shellmate-ai ask "$question"
  elif [[ -n "$SHELLMATE_LAST_COMMAND" ]]; then
    # 空缓冲：自动解释上一条命令（结合退出码定位失败原因）。
    export SHELLMATE_LAST_COMMAND SHELLMATE_LAST_EXIT
    command shellmate-ai explain-last
  fi
  zle reset-prompt 2>/dev/null
}
zle -N shellmate-widget
bindkey '^G' shellmate-widget

# 用管道重跑上一条命令，把完整输出喂给 agent 解释（命令失败后的 Ctrl-X）。
shellmate-rerun-explain() {
  local cmd="$SHELLMATE_LAST_COMMAND"
  if [[ -z "$cmd" ]]; then
    print -P "%F{red}没有可重跑的上一条命令。%f" >&2
    return
  fi
  zle -I
  print -P "%F{yellow}重跑并解释：${cmd}%f" >&2
  # 重跑可能有副作用，因此由用户显式按键触发；输出经管道交给 agent，不再回显。
  eval "$cmd" 2>&1 | command shellmate-ai explain
  zle reset-prompt 2>/dev/null
}
zle -N shellmate-rerun-explain
bindkey '^X' shellmate-rerun-explain
