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
  # 必须第一个读取 $?：本函数体内执行的任何命令都会覆盖它。
  local last_exit=$?
  # precmd 在每条命令结束后、显示提示符前执行，$? 即上一条命令的退出码。
  # Shellmate 自身被调用时（在提示符里执行 shellmate-ai）不更新上一条真实命令的
  # 退出码，否则会把 Shellmate 的成败当成上一条命令的成败。
  if [[ $SHELLMATE_INTERNAL_COMMAND -eq 1 ]]; then
    SHELLMATE_INTERNAL_COMMAND=0
    return
  fi
  SHELLMATE_LAST_EXIT=$last_exit
  # 真实命令失败时，在提示符上方提示可重跑并让 agent 看完整报错。
  if [[ $last_exit -ne 0 && -n "$SHELLMATE_LAST_COMMAND" ]]; then
    print -P "%F{yellow}⚠ 上一条命令失败 (exit $last_exit)%f"
    print -P "%F{yellow}  按 Ctrl-X 重跑并把报错交给 agent；按 Ctrl-G 只用命令和退出码解释%f"
  fi
}

autoload -Uz add-zsh-hook
add-zsh-hook preexec shellmate-preexec
add-zsh-hook precmd shellmate-precmd

# 读取近期历史，供各 widget 通过 --history 传给 CLI。
# 不用环境变量传递：导出的变量会被之后启动的所有子进程继承，等于泄漏 shell 历史。
shellmate-history() {
  local lines
  lines="$(command shellmate-ai history-lines 2>/dev/null || print 20)"
  # 用 zsh 内置 fc 命令获取最近历史；历史可能含换行，作为参数传递是安全的。
  fc -ln -${lines} 2>/dev/null
}

shellmate-widget() {
  local history_text question
  history_text="$(shellmate-history)"
  # 用户先在命令行输入问题，按 Ctrl-G 时读取当前行作为问题。
  question="$BUFFER"
  # 清空当前行，避免回答输出与问题混在一起。
  BUFFER=""
  CURSOR=0
  zle -I
  if [[ -n "$question" ]]; then
    # -- 之后的内容不会被当成选项，避免问题以 - 开头时被解析成参数。
    command shellmate-ai ask --history "$history_text" -- "$question"
  elif [[ -n "$SHELLMATE_LAST_COMMAND" ]]; then
    # 空缓冲：自动解释上一条命令（结合退出码定位失败原因）。
    command shellmate-ai explain-last --history "$history_text" \
      --last-command "$SHELLMATE_LAST_COMMAND" --last-exit "$SHELLMATE_LAST_EXIT"
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
  eval "$cmd" 2>&1 | command shellmate-ai explain --history "$(shellmate-history)"
  zle reset-prompt 2>/dev/null
}
zle -N shellmate-rerun-explain
bindkey '^X' shellmate-rerun-explain
