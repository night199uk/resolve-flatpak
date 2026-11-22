# AMD GPU troubleshooting

This guide covers GPU problems with AMD cards under resolve-flatpak. It applies
to the `.flatpak` bundles and to the FlatPark package. Replace
`com.blackmagic.Resolve` with `com.blackmagic.ResolveStudio` if you use Studio.

## How Resolve uses an AMD GPU

- Resolve uses OpenGL for its interface and **OpenCL** for GPU compute. On AMD
  it does not use CUDA, and it does not use HIP directly.
- The Flatpak sandbox does **not** inherit the host's OpenCL installation.
  Resolve sees the Mesa and OpenCL stack that Flatpak binds into the sandbox.
- The two packages use different base runtimes, but both are built on
  Freedesktop SDK **26.08**, and the current ROCm Runtime works with both:
  - the `.flatpak` bundles use `org.gnome.Platform` **51**;
  - the FlatPark package uses `org.freedesktop.Platform` **26.08**.
- There are two practical ways to provide OpenCL:
  1. **Mesa RustICL**, shipped by the GL driver extension
     (`org.freedesktop.Platform.GL.default`). This is enabled by default: both
     manifests set `RUSTICL_ENABLE=radeonsi,iris,nouveau`, and RustICL is
     present in the 26.08 GL extension. RustICL support in Resolve is patchy,
     however, and does not work on all AMD cards.
  2. **AMD ROCm OpenCL**, via the
     [rocm-flatpak](https://github.com/night199uk/rocm-flatpak) runtime
     extension. The current ROCm Runtime is a self-contained extension on the
     `1.4` branch that ships its own AMD Mesa, so it works with both the
     GNOME 51 `.flatpak` runtime and the FlatPark (26.08) runtime. Use it when
     RustICL fails.
- The host's `clinfo` output is **not** what Resolve sees. Always check inside
  the sandbox.

Clover (Mesa's older OpenCL implementation) is generally not usable by Resolve.
If `clinfo` reports only Clover, that is the usual explanation for an
"Unsupported GPU processing mode" error; use RustICL or ROCm instead.

## Symptom to likely cause

| Symptom | Likely cause |
| --- | --- |
| "Unsupported GPU processing mode", no GPUs in the dropdown, or `No matched GPUs found` in the log | No usable OpenCL platform inside the sandbox |
| Resolve starts and then exits or crashes at the splash screen | OpenGL/GPU access problem, or a driver mismatch |
| GPU is listed but processing stays slow or the compute API is `Unknown` | OpenCL not selected, ROCm device hidden, or the wrong GPU selected |
| RustICL is present but Resolve still finds no GPU, or crashes on some cards | RustICL support is incomplete; use ROCm |
| `bwrap: Can't get type of source /dev/kfd: Permission denied` | Flatpak 1.18 plus the SELinux `staff_u` bug |

## 1. Check Flatpak and GPU permissions

Check the app's permissions:

```sh
flatpak info --show-permissions com.blackmagic.Resolve
```

You want to see:

```ini
[Context]
devices=dri;
```

If the line is missing or negated, enable **Device -> GPU** in Flatseal, or
run:

```sh
flatpak override --user --device=dri com.blackmagic.Resolve
```

Show any environment or device overrides that have been added. Use `--user`
and/or `--system`; a plain `flatpak override --show` does not display
user overrides for a system-installed app:

```sh
flatpak override --user --show com.blackmagic.Resolve
flatpak override --system --show com.blackmagic.Resolve
```

A stray `OCL_ICD_VENDORS`, `FLATPAK_GL_DRIVERS`, or `--nodevice=dri` here is a
common cause of a regression. `OCL_ICD_VENDORS` is obsolete: current ROCm
Runtime builds no longer need it, so remove any override (section 5). An
override that sets `RUSTICL_ENABLE` to an empty value also wins over the
manifest's `RUSTICL_ENABLE=radeonsi`, so check for that if GPU detection used
to work.

## 2. Check inside the sandbox

Open a shell in the app's sandbox:

```sh
flatpak run --devel --command=sh com.blackmagic.Resolve
```

Then check the devices, environment, and OpenCL vendor files:

```sh
ls -l /dev/dri /dev/kfd
env | grep -E 'RUSTICL|OCL_ICD|FLATPAK_GL|LIBVA'
ls -l /usr/lib/x86_64-linux-gnu/GL/
ls -l /usr/lib/x86_64-linux-gnu/GL/OpenCL/vendors/
find /usr/lib/x86_64-linux-gnu/GL \( -iname '*rusticl*' -o -iname '*opencl*' \)
ldconfig -p | grep -iE 'rusticl|opencl'
ls -l /usr/lib/x86_64-linux-gnu/GL/ROCm/bin/ 2>/dev/null
```

Notes:

- `/dev/dri/renderD128` must exist. If it does not, the sandbox has no GPU at
  all, and neither OpenGL nor OpenCL can work.
- `/dev/kfd` is only needed for ROCm. Flatpak 1.18 and newer include it in the
  `dri` device permission; older versions need `--device=all`.
- RustICL needs its ICD. In practice those files are:
  - `.../GL/default/lib/libRusticlOpenCL.so.1`
  - `.../GL/OpenCL/vendors/rusticl.icd`, containing `libRusticlOpenCL.so.1`

  If neither exists, the runtime cannot offer OpenCL through RustICL.
- If `OCL_ICD_VENDORS` is set, it is an old ROCm workaround. Current ROCm
  Runtime builds no longer need it; remove the override (section 5). A stale
  value that points at a missing directory makes the loader find **zero**
  platforms.

### ROCm Runtime tools

The ROCm Runtime ships its own `clinfo` and `rocminfo`, and they run inside the
same sandbox Resolve uses. After installing ROCm and setting
`FLATPAK_GL_DRIVERS=ROCm` (section 5), open the app sandbox and run:

```sh
ROCM=/usr/lib/x86_64-linux-gnu/GL/ROCm
$ROCM/bin/rocminfo
$ROCM/bin/clinfo
```

`rocminfo` should show an agent for the card:

```text
Agent 2
  Name:                    gfx1100
  Marketing Name:          AMD Radeon RX 7900 XTX
  Vendor Name:             AMD
  ...
```

`clinfo` should show the AMD OpenCL platform and the same GPU:

```text
  Platform Name                                   AMD Accelerated Parallel Processing
  Platform Vendor                                 Advanced Micro Devices, Inc.
  ...
  Device Name                                     gfx1100
```

The exact platform count depends on whether the runtime's Mesa build also
exposes RustICL. What matters is that your `gfx*` card appears. If the binaries
are missing, either the ROCm extension is not bound (section 5) or the installed
ROCm Runtime predates the bundled tools; update to the latest rocm-flatpak
release.

## 3. Read Resolve's log

The launcher sets `DAVINCI_RESOLVE_LOG_DIR` to the install prefix's `logs`
directory. For both the `.flatpak` bundles and the FlatPark package this is:

```sh
ls -lt ~/.var/app/com.blackmagic.Resolve/data/logs | head
grep -E 'GPUDetect|GPUConfig|OpenCL|OpenGL' \
  ~/.var/app/com.blackmagic.Resolve/data/logs/DaVinci-Resolve-*.log | tail -n 60
```

A failed GPU setup looks like this:

```text
GPUDetect | ERROR | No matched GPUs found.
Main.GPUConfig | INFO | Compute API set to automatic, defaulting to Unknown.
Main.GPUConfig | ERROR | Failed to select a valid compute API.
Main.GPUConfig | ERROR | No GPUs selected!
```

`No matched GPUs found` combined with `Unknown` compute API means Resolve could
not see an OpenCL platform. It is an OpenCL problem, not necessarily an OpenGL
problem. If the same log also shows an OpenGL failure, check `/dev/dri` and the
GPU permission first.

## 4. Fix: use RustICL

RustICL is the default path, but its support in Resolve is patchy and
card-dependent. It does not work on every AMD card. If GPU detection still
fails after the checks below, use ROCm (section 5) instead.

Confirm the effective environment still contains the variable:

```sh
flatpak info --show-permissions com.blackmagic.Resolve | grep RUSTICL
```

The manifest sets `RUSTICL_ENABLE=radeonsi,iris,nouveau`. If the output shows
`RUSTICL_ENABLE=` with no value, an override is clearing it. Set it explicitly:

```sh
flatpak override --user --env=RUSTICL_ENABLE=radeonsi com.blackmagic.Resolve
```

Then update the runtime and relaunch:

```sh
flatpak update
flatpak run com.blackmagic.Resolve
```

If it still fails, check that the GL extension provides the RustICL ICD, as
described in section 2, and that the GPU is actually an AMD card. When the ICD
is missing, or the card still is not detected, use ROCm (section 5); it works
with both packages.

RustICL works best on GCN 1.2 and newer cards (Polaris, Vega, RDNA). Pre-GCN
cards can only use software rendering or the older AMD OpenCL stacks.

## 5. Fix: use ROCm OpenCL

RustICL is the default, but its Resolve support is patchy. When it fails, use
the AMD ROCm OpenCL runtime from
[rocm-flatpak](https://github.com/night199uk/rocm-flatpak).

The current ROCm Runtime is a self-contained extension on the `1.4` branch: it
ships its own AMD Mesa and libdrm instead of layering on the runtime's default
Mesa. Because the `1.4` branch is accepted by both the GNOME 51 `.flatpak`
runtime and the 26.08 FlatPark runtime, it binds to either package. You no
longer need to match the Freedesktop SDK branch.

Install the latest rocm-flatpak release into the same Flatpak installation as
the app. The FlatPark package is normally system-installed, so use `--system`
for the ROCm extension as well; a user-installed extension is not picked up by
a system app. Check that it is present:

```sh
flatpak --version                   # 1.18+ for /dev/kfd with --device=dri
flatpak install ./rocm-flatpak-*.flatpak
flatpak list | grep ROCm
```

Remove the old `OCL_ICD_VENDORS` workaround if you added it. The current ROCm
Runtime no longer needs it, and a stale value can hide the OpenCL platforms:

```sh
flatpak override --user --unset-env=OCL_ICD_VENDORS com.blackmagic.Resolve
# for a system-wide override:
sudo flatpak override --unset-env=OCL_ICD_VENDORS com.blackmagic.Resolve
```

Tell Flatpak to load the ROCm GL extension. Use `ROCm`, not the old
`ROCm:default`; the ROCm Runtime now provides the graphics stack itself. The
rocm-flatpak project recommends a login environment file:

```sh
mkdir -p ~/.config/environment.d
echo 'FLATPAK_GL_DRIVERS=ROCm' \
  > ~/.config/environment.d/60-flatpak-gl-drivers.conf
```

Log out and back in after creating that file. `FLATPAK_GL_DRIVERS` is global to
Flatpak; if it breaks other apps, set it only for the Resolve launch instead:

```sh
export FLATPAK_GL_DRIVERS=ROCm
flatpak run com.blackmagic.Resolve
```

Make sure the device permission covers `/dev/kfd`:

```sh
# Flatpak 1.18 and newer: dri includes /dev/kfd
flatpak override --user --device=dri com.blackmagic.Resolve

# Flatpak older than 1.18
flatpak override --user --device=all com.blackmagic.Resolve
```

Verify that Flatpak actually binds the ROCm extension. Run verbosely and look
for the ROCm bind mount:

```sh
flatpak run -vv --devel --command=sh com.blackmagic.Resolve
```

The verbose output should contain a ro-bind for the ROCm extension (the runtime
path is `/var/lib/flatpak` for a system install and `~/.local/share/flatpak`
for a user install):

```text
F: --ro-bind
F: /var/lib/flatpak/runtime/org.freedesktop.Platform.GL.ROCm/x86_64/1.4/.../files
F: /usr/lib/x86_64-linux-gnu/GL/ROCm
```

Inside that shell, the ROCm directory and a vendor file should exist:

```sh
ls -l /usr/lib/x86_64-linux-gnu/GL/ROCm
ls -l /usr/lib/x86_64-linux-gnu/GL/OpenCL/vendors/
```

The runtime's own `rocminfo` and `clinfo` should also be there; run them as
described in section 2 to confirm that the extension is bound and that ROCm
sees the GPU.

If the ROCm ro-bind or `/usr/lib/x86_64-linux-gnu/GL/ROCm` is missing, the
extension is not bound. Reinstall the latest rocm-flatpak release into the same
installation and run `flatpak update`. With the current `1.4` branch there is
no Freedesktop SDK branch to match.

ROCm officially supports a limited set of cards. Check AMD's compatibility
matrix for your GPU. For pre-Vega cards, ROCm also needs:

```sh
flatpak override --user --env=ROC_ENABLE_PRE_VEGA=1 com.blackmagic.Resolve
```

## 6. Select the right GPU

On multi-GPU systems, the wrong GPU may be picked:

- In Resolve, open **Preferences -> System -> Memory and GPU** and check the GPU
  list. Remove any stale entry and rescan.
- For a hybrid laptop where the discrete GPU is second, try:

  ```sh
  flatpak override --user --env=DRI_PRIME=1 com.blackmagic.Resolve
  ```

- To pin a specific card, use its PCI address:

  ```sh
  flatpak override --user --env=DRI_PRIME=pci-0000_03_00_0 com.blackmagic.Resolve
  ```

  Find the address with `lspci` and match it against
  `/dev/dri/by-path/` inside the sandbox.
- For ROCm, restrict the visible device:

  ```sh
  flatpak override --user --env=ROCR_VISIBLE_DEVICES=0 com.blackmagic.Resolve
  ```

## 7. Hardware video decode (VA-API)

VA-API is separate from OpenCL. Resolve uses the GPU primarily for compute, and
its Linux hardware encode/decode support is more limited than the CUDA/NVENC
path on NVIDIA. Do not assume a VA-API problem is why GPU compute is missing.

The Mesa build in the sandbox ships AMD's VA-API driver
(`radeonsi_drv_video.so`), and `/dev/dri` is already exposed by the GPU
permission. To test VA-API support, run `vainfo` on the host. Host-side VA-API
drivers are not automatically available inside the sandbox.

## 8. Known sandbox problems

### `/dev/kfd` permission error on SELinux `staff_u`

Flatpak 1.18 added `/dev/kfd` to the `dri` device permission. On Fedora systems
with the login user mapped to `staff_u`, bwrap can fail while probing the node:

```text
bwrap: Can't get type of source /dev/kfd: Permission denied
```

This is an SELinux policy issue, not a Resolve issue. Workarounds:

- use `--device=all` for the app, or
- update to a Flatpak build that skips inaccessible optional device nodes, or
- fix the SELinux policy.

Upstream references:
[flatpak/flatpak#6690](https://github.com/flatpak/flatpak/issues/6690),
[fedora-selinux/selinux-policy#3238](https://github.com/fedora-selinux/selinux-policy/issues/3238).

### ROCm on Flatpak older than 1.18

`--device=dri` does not expose `/dev/kfd` before Flatpak 1.18. ROCm then reports
no devices. Add `--device=all` for the app, as shown in section 5.

## 9. What to include in a bug report

Open an issue at
[night199uk/resolve-flatpak](https://github.com/night199uk/resolve-flatpak/issues)
with the output of:

```sh
flatpak --version
flatpak list --app --runtime | grep -E 'Resolve|ROCm|Platform'
flatpak info com.blackmagic.Resolve
flatpak info --show-permissions com.blackmagic.Resolve
flatpak override --user --show com.blackmagic.Resolve
flatpak override --system --show com.blackmagic.Resolve
printenv FLATPAK_GL_DRIVERS
uname -r
lspci -nn | grep -Ei 'vga|3d|display'
glxinfo -B
clinfo | grep -E 'Platform (Name|Version)|Device Name'
grep -E 'GPUDetect|GPUConfig' \
  ~/.var/app/com.blackmagic.Resolve/data/logs/DaVinci-Resolve-*.log | tail -n 60
```

If you use ROCm, also include the output of
`/usr/lib/x86_64-linux-gnu/GL/ROCm/bin/rocminfo` and
`/usr/lib/x86_64-linux-gnu/GL/ROCm/bin/clinfo` from inside the app sandbox.

Attach the full Resolve log rather than a screenshot of the error dialog. Also
mention whether you use the `.flatpak` bundle or the FlatPark package, and which
OpenCL route you tried (RustICL or ROCm).
