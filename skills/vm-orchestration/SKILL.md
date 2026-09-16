---
name: vm-orchestration
description: Create/manage VMs and run agents inside them; disposable test envs.
---

# vm-orchestration

- Provision: VirtualBox (`VBoxManage`), QEMU/KVM, Vagrant (`Vagrantfile` + `vagrant up`), or a cloud VM.
- Lifecycle: create → snapshot → run → restore/destroy. Snapshots = cheap clean state.
- Shared storage for multi-agent: mount the SAME host folder into each VM
  (VirtualBox shared folders / 9p / NFS) so agents share one workspace.
- Run an agent inside: install it in the guest, auto-apply skills/CLAUDE.md on boot.
- Expose the screen: VNC / MJPEG / WebRTC → point a subagent's `vm.stream` at it.
This is the path to give each subagent its own machine but one shared data set.
