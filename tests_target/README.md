# Ubuntu systemd 目标测试

该测试必须运行真实 systemd PID 1，并建立 `localflow` 用户管理器。构建和启动：

```bash
docker build -f tests_target/Dockerfile.systemd -t localflow-systemd-test .
docker run --privileged --name localflow-systemd-test -d \
  --tmpfs /run --tmpfs /run/lock \
  -v /sys/fs/cgroup:/sys/fs/cgroup:rw \
  -v "$PWD:/work" localflow-systemd-test
```

随后在容器内安装仓库、建立用户、启用 linger，并运行 `test_systemd_lifecycle.py`。没有 `systemd --system --running` 成功结果时测试会跳过且质量指标不能转为通过。
