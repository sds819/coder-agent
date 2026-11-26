# 沙箱

agent 的命令跑在沙箱里。默认的沙箱就是用户自己的机器。

```yaml
sandbox:
  type: local
```

## 远端的沙箱

那些沙箱是随 mini-swe-agent 一起搬过来的，照原样使用：

| `sandbox.type` | 它做什么 |
|---|---|
| `local` | 命令跑在这台机器上 |
| `docker` | 一个 Docker 容器 |
| `singularity` | 一个 Singularity 容器 |
| `swerex_docker` | SWE-ReX 管的 Docker 容器 |
| `swerex_modal` | Modal 上的一个容器 |
| `bubblewrap` | 一个不需要 root 的沙箱 |
| `contree` | 一个不需要 root 的容器 |

远端的沙箱是随 mini-swe-agent 一起搬过来的那些环境：coding agent 不自己写容器。
它们要 extra `sandbox` 里的那些包：

```bash
pip install 'coder-agent[sandbox]'
```

没有那些包，本地的沙箱照样能用；远端的那个会说出缺的是哪个包。

```yaml
sandbox:
  type: swerex_docker
  image: python:3.11
```

环境不认识的选项会被忽略，所以同一份配置对每一种沙箱都管用。类的完整路径也
行得通，那是用自己写的环境的办法：

```yaml
sandbox:
  type: my_package.my_module.MyEnvironment
```

远端沙箱的凭据（`SWE_REX_SERVER_URL`、`SWE_REX_API_KEY`……）来自环境变量或
`.env` 文件。

容器有自己的目录，不是会话的目录：宿主上的路径在容器里不存在。给容器一个
它自己的目录：

```yaml
sandbox:
  type: swerex_docker
  image: python:3.11
  cwd: /workspace
```

## 沙箱的三档

本地的沙箱有三档。它们说的是 agent 的命令在这台机器上能做什么，而且由
**操作系统**来执行：macOS 上是 Seatbelt 的配置文件，Linux 上是 bubblewrap 的
命名空间。越界的命令是被内核挡下来的，不是被文件里的一条规则挡下来的。

```yaml
sandbox:
  type: local
  mode: workspace-write
```

| `sandbox.mode` | 命令能做什么 |
|---|---|
| `full-access` | 用户能做的都能做。默认档。 |
| `workspace-write` | 磁盘可以读，只能在工作目录里写 |
| `read-only` | 磁盘可以读，不能写 |

这一档和权限模式是**两条正交的轴**：权限那一层会问用户，沙箱这一层谁都不问。
`bypass` 跳过的是提问，不是磁盘的边界——闸和沙箱是两层，不二选一。

`read-only` 这一档连写文件的工具（`write`、`edit`、`multi_edit`）一起拒掉：
它们写的是用户的机器，在沙箱外面。用户自己写的规则也放宽不了这个。

命令可以写的目录是工作目录，加上 `permissions.include_dirs` 里那些。系统
的临时目录一直可以写——构建总得有个地方放东西。

`permissions.network` 是 `deny` 的时候，网络在操作系统那一层也是关着的：沙箱
没有出路。

项目可以关沙箱，不能开沙箱。两档里更紧的那一档算数，所以一个要求
`read-only` 的仓库，不管用户那层怎么写，agent 都写不了东西。
项目也不能决定命令**在哪里**跑：沙箱的 `type` 和环境的那些选项（`image` 等等）
都会从项目的配置里被丢掉——项目的环境会把用户的工作目录一起带走。

### 沙箱需要什么

| 系统 | 用什么 |
|---|---|
| macOS | Seatbelt（`sandbox-exec`），系统自带 |
| Linux | bubblewrap（`bwrap`），要自己装 |

没有那个程序，会话就起不来：承诺兑现不了，就不要许。

验证用的命令是你自己的命令，不是 agent 的：它们按你的身份跑，在沙箱外面。

## 界面上的样子

界面顶上那条栏在沙箱不是本地的时候会报出它的名字，`/sandbox` 给出整份配置：

```
type: swerex_docker
mode: full-access
image: python:3.11
environment: swerex_docker
```

生效的选项列在类型和环境之间。

## 环境自己没有策略

远端的沙箱是随 mini-swe-agent 一起搬过来的环境，所以它们没有网络策略，也没有可写目录的
清单。网络策略是环境的属性，写在环境那里——用环境认识的那些选项。`docker`
沙箱吃的是 `docker` 命令的参数：

```yaml
sandbox:
  type: docker
  image: python:3.11
  run_args: ["--rm", "--network", "none"]
```

每个沙箱有各自的选项：比如 `swerex_docker` 那个收 `deployment_extra_kwargs`，
是给 SWE-ReX 部署用的。环境不认识的选项会被忽略，所以写在 `swerex_docker`
下面的 `run_args` 悄无声息地就没了。

agent 能碰哪些路径是 agent 的属性，不是容器的。它们由权限那一层圈住：
`permissions.deny_paths` 是不能碰的路径，`permissions.include_dirs` 是会话目录
之外、但允许碰的那些。被禁的路径对命令行也一样：禁掉 `*.env` 之后，
`cat .env` 也被拒。本地沙箱的那一档，是把同样的事告诉操作系统。

配置里还留着 `sandbox.network` 或 `sandbox.writable_roots` 也能跑：它们现在是
不认识的选项，而不认识的选项会被忽略。

## 还是本地的那些

读写文件的工具（`read`、`write`、`edit`……）动的是用户机器上的文件，因为
沙箱环境只跑命令。只有 `bash` 工具的命令进沙箱。

`read-only` 那一档把写文件的工具也拒了：它们写的是用户的机器，在沙箱外面。

随 mini-swe-agent 一起搬过来的那个魔法——命令打印 `COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT`
就算任务结束——在远端沙箱里也是关掉的：coding agent 的一轮是模型说结束才结束。
