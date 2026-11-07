#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import glob
import gc
import json
import os
import re
import socket
import struct
import subprocess
import sys
import time

LANG = "en"
ROOT = {}
_IDS = {}


def detect_lang():
    for v in ("LC_ALL", "LC_MESSAGES", "LANGUAGE", "LANG"):
        s = os.environ.get(v, "")
        if s:
            return "tr" if s.lower().startswith("tr") else "en"
    return "en"


def L(en, tr):
    return tr if LANG == "tr" else en


def res(p):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, p)


def rd(p):
    try:
        with open(p, errors="ignore") as f:
            return f.read().strip()
    except Exception:
        return ""


def rlink(p):
    try:
        return os.path.basename(os.readlink(p))
    except Exception:
        return ""


def human(n, dec=False):
    b = 1000.0 if dec else 1024.0
    u = ("B", "KB", "MB", "GB", "TB") if dec else ("B", "KiB", "MiB", "GiB", "TiB")
    n = float(n)
    for x in u[:-1]:
        if n < b:
            return f"{n:.0f} {x}" if x == "B" else f"{n:.1f} {x}"
        n /= b
    return f"{n:.1f} {u[-1]}"


def add(rows, k, v, st=None):
    if v not in ("", None):
        rows.append((k, str(v), st))


def H(t):
    return (t, None, None)


def note(t):
    return ("", t, "note")


def pci_lookup(pairs):
    need = [p for p in set(pairs) if p not in _IDS]
    if not need:
        return
    want = {}
    for v, d in need:
        want.setdefault(v, set()).add(d)
    maxv = max(want)
    vnames = {}
    try:
        cur = None
        with open(res("pci.ids"), errors="ignore") as f:
            for line in f:
                if line[0] == "\t":
                    if cur is not None and len(line) > 7:
                        try:
                            did = int(line[1:5], 16)
                        except ValueError:
                            continue
                        if did in want[cur]:
                            _IDS[(cur, did)] = (vnames[cur], line[7:].strip())
                else:
                    try:
                        vid = int(line[:4], 16)
                    except ValueError:
                        continue
                    if vid > maxv:
                        break
                    cur = vid if vid in want else None
                    if cur is not None:
                        vnames[vid] = line[6:].strip()
    except Exception:
        pass
    for v, d in need:
        if (v, d) not in _IDS:
            _IDS[(v, d)] = (vnames.get(v, f"{v:04x}"), f"{d:04x}")


def vshort(s):
    if "[" in s:
        s = s[s.find("[") + 1:s.find("]")]
    for x in (" Co., Ltd.", " Corporation", " Corp.", " Inc.", " Ltd.", ",", " Semiconductor", " Technology"):
        s = s.replace(x, "")
    return s.strip()


def pci_name(v, d):
    pci_lookup([(v, d)])
    vn, dn = _IDS[(v, d)]
    if "[" in dn:
        dn = dn[dn.rfind("[") + 1:dn.rfind("]")]
    return f"{vshort(vn)} {dn}"


def pci_devices():
    out = []
    for d in sorted(glob.glob("/sys/bus/pci/devices/*")):
        try:
            out.append({"addr": os.path.basename(d),
                        "v": int(rd(d + "/vendor"), 16), "d": int(rd(d + "/device"), 16),
                        "cls": int(rd(d + "/class"), 16), "drv": rlink(d + "/driver"),
                        "path": d})
        except ValueError:
            pass
    return out


def t_system():
    osr = {}
    for line in rd("/etc/os-release").splitlines():
        k, _, v = line.partition("=")
        osr[k] = v.strip('"')
    up = float(rd("/proc/uptime").split()[0] or 0)
    d, h, m = int(up // 86400), int(up % 86400 // 3600), int(up % 3600 // 60)
    u = os.uname()
    r = [H(L("Operating system", "İşletim sistemi"))]
    add(r, L("Distribution", "Dağıtım"), osr.get("PRETTY_NAME"))
    add(r, L("Kernel", "Çekirdek"), u.release)
    add(r, L("Architecture", "Mimari"), u.machine)
    add(r, L("Hostname", "Bilgisayar adı"), u.nodename)
    add(r, L("Uptime", "Çalışma süresi"), (f"{d} " + L("d ", "g ") if d else "") + f"{h} " + L("h ", "sa ") + f"{m} " + L("min", "dk"))
    add(r, L("Boot mode", "Önyükleme modu"), "UEFI" if os.path.exists("/sys/firmware/efi") else "Legacy BIOS")
    r.append(H(L("Desktop", "Masaüstü")))
    add(r, L("Desktop environment", "Masaüstü ortamı"), os.environ.get("XDG_CURRENT_DESKTOP"))
    add(r, L("Session type", "Oturum türü"), os.environ.get("XDG_SESSION_TYPE"))
    return r


def t_cpu():
    info = rd("/proc/cpuinfo")
    blocks = [b for b in info.split("\n\n") if b.strip()]
    f, mhz, phys = {}, [], set()
    for i, b in enumerate(blocks):
        for line in b.splitlines():
            k, _, v = line.partition(":")
            k, v = k.strip(), v.strip()
            if i == 0:
                f[k] = v
            if k == "cpu MHz":
                mhz.append(v)
            elif k == "physical id":
                phys.add(v)
    c0 = "/sys/devices/system/cpu/cpu0/"
    r = [H(L("Processor", "İşlemci"))]
    add(r, L("Model", "Model"), f.get("model name") or f.get("Hardware"))
    add(r, L("Vendor", "Üretici"), f.get("vendor_id"))
    if f.get("cpu family"):
        add(r, L("Family / Model / Stepping", "Aile / Model / Stepping"),
            f"{f.get('cpu family')} / {f.get('model')} / {f.get('stepping')}")
    add(r, "Microcode", f.get("microcode"))
    sock = max(1, len(phys))
    try:
        add(r, L("Physical cores", "Fiziksel çekirdek"), int(f["cpu cores"]) * sock)
    except Exception:
        pass
    add(r, L("Threads", "Mantıksal işlemci"), len(blocks))
    add(r, L("Sockets", "Soket"), sock)
    lo, hi = rd(c0 + "cpufreq/cpuinfo_min_freq"), rd(c0 + "cpufreq/cpuinfo_max_freq")
    if lo and hi:
        add(r, L("Frequency range", "Frekans aralığı"), f"{int(lo) // 1000} – {int(hi) // 1000} MHz")
    add(r, L("Scaling driver", "Frekans sürücüsü"), rd(c0 + "cpufreq/scaling_driver"))
    add(r, "Governor", rd(c0 + "cpufreq/scaling_governor"))
    tr = {"Data": "Veri", "Instruction": "Komut", "Unified": "Birleşik"}
    r.append(H(L("Cache", "Önbellek")))
    for d in sorted(glob.glob(c0 + "cache/index*")):
        ty = rd(d + "/type")
        add(r, f"L{rd(d + '/level')} {tr.get(ty, ty) if LANG == 'tr' else ty}", rd(d + "/size"))
    fl = set(f.get("flags", "").split())
    key = [x for x in ("sse4_1", "sse4_2", "avx", "avx2", "avx512f", "aes", "fma", "bmi2", "vmx", "svm") if x in fl]
    if key:
        r.append(H(L("Features", "Özellikler")))
        add(r, L("Instruction sets", "Komut setleri"), ", ".join(key))
        virt = "Intel VT-x" if "vmx" in fl else "AMD-V" if "svm" in fl else L("not available", "yok")
        add(r, L("Virtualization", "Sanallaştırma"), virt)
    if mhz:
        r.append(H(L("Live core frequencies", "Anlık çekirdek frekansları")))
        for i, m in enumerate(mhz):
            add(r, L(f"Core {i}", f"Çekirdek {i}"), f"{float(m):.0f} MHz")
    return r


def t_mem():
    mi = {}
    for line in rd("/proc/meminfo").splitlines():
        k, _, v = line.partition(":")
        p = v.split()
        mi[k] = int(p[0]) * 1024 if p else 0
    tot, av = mi.get("MemTotal", 0), mi.get("MemAvailable", 0)
    r = [H(L("Memory (RAM)", "Bellek (RAM)"))]
    add(r, L("Total", "Toplam"), human(tot))
    add(r, L("Used", "Kullanılan"), f"{human(tot - av)}  (%{(tot - av) * 100 // max(tot, 1)})")
    add(r, L("Available", "Kullanılabilir"), human(av))
    add(r, L("Cached", "Önbellek"), human(mi.get("Cached", 0)))
    st, sf = mi.get("SwapTotal", 0), mi.get("SwapFree", 0)
    add(r, "Swap", f"{human(st - sf)} / {human(st)}" if st else L("none", "yok"))
    if ROOT.get("ram"):
        for m in ROOT["ram"]:
            r.append(H(f"{L('Module', 'Modül')}: {m['loc']}"))
            add(r, L("Size", "Boyut"), human(m["mib"] * 1048576))
            add(r, L("Type", "Tür"), f"{m['type']} {m['form']}".strip())
            add(r, L("Speed", "Hız"), f"{m['speed']} MT/s" if m["speed"] else "")
            add(r, L("Running at", "Çalışma hızı"), f"{m['cfg']} MT/s" if m["cfg"] else "")
            add(r, L("Manufacturer", "Üretici"), m["mfr"])
            add(r, L("Part number", "Parça no"), m["part"])
    else:
        r.append(note(L("Press “Unlock details” for per-module info (type, speed, manufacturer, part number).",
                        "Modül bilgisi (tür, hız, üretici, parça no) için “Ayrıntıları aç” butonuna bas.")))
    return r


def t_board():
    b = "/sys/class/dmi/id/"
    ch = {"3": "Desktop", "4": "Low Profile Desktop", "6": "Mini Tower", "7": "Tower", "8": "Portable", "9": "Laptop",
          "10": "Notebook", "13": "All-in-One", "30": "Tablet", "31": "Convertible", "35": "Mini PC"}
    r = [H(L("Motherboard", "Anakart"))]
    add(r, L("Vendor", "Üretici"), rd(b + "board_vendor"))
    add(r, L("Model", "Model"), rd(b + "board_name"))
    add(r, L("Version", "Sürüm"), rd(b + "board_version"))
    r.append(H("BIOS / Firmware"))
    add(r, L("Vendor", "Üretici"), rd(b + "bios_vendor"))
    add(r, L("Version", "Sürüm"), rd(b + "bios_version"))
    add(r, L("Date", "Tarih"), rd(b + "bios_date"))
    add(r, L("Boot mode", "Önyükleme modu"), "UEFI" if os.path.exists("/sys/firmware/efi") else "Legacy BIOS")
    r.append(H(L("System", "Sistem")))
    add(r, L("Vendor", "Üretici"), rd(b + "sys_vendor"))
    add(r, L("Product", "Ürün"), rd(b + "product_name"))
    add(r, L("Chassis", "Kasa"), ch.get(rd(b + "chassis_type"), rd(b + "chassis_type")))
    return r


def nvml():
    import ctypes as C
    try:
        lib = C.CDLL("libnvidia-ml.so.1")
        if lib.nvmlInit_v2() != 0:
            return None, []
    except Exception:
        return None, []

    def g(fn, *a):
        try:
            return getattr(lib, fn)(*a) == 0
        except Exception:
            return False

    class Mem(C.Structure):
        _fields_ = [("total", C.c_ulonglong), ("free", C.c_ulonglong), ("used", C.c_ulonglong)]

    class Util(C.Structure):
        _fields_ = [("gpu", C.c_uint), ("mem", C.c_uint)]

    drv = C.create_string_buffer(96)
    g("nvmlSystemGetDriverVersion", drv, 96)
    cnt, out = C.c_uint(), []
    if g("nvmlDeviceGetCount_v2", C.byref(cnt)):
        for i in range(cnt.value):
            h, d = C.c_void_p(), {}
            if not g("nvmlDeviceGetHandleByIndex_v2", i, C.byref(h)):
                continue
            nm = C.create_string_buffer(96)
            if g("nvmlDeviceGetName", h, nm, 96):
                d["name"] = nm.value.decode()
            m = Mem()
            if g("nvmlDeviceGetMemoryInfo", h, C.byref(m)):
                d["vram"] = f"{human(m.used)} / {human(m.total)}"
            u = Util()
            if g("nvmlDeviceGetUtilizationRates", h, C.byref(u)):
                d["util"] = f"%{u.gpu}  (VRAM %{u.mem})"
            x = C.c_uint()
            if g("nvmlDeviceGetTemperature", h, 0, C.byref(x)):
                d["temp"] = f"{x.value} °C"
            for key, t in (("gr", 0), ("mem", 2)):
                mx = C.c_uint()
                if g("nvmlDeviceGetClockInfo", h, t, C.byref(x)):
                    g("nvmlDeviceGetMaxClockInfo", h, t, C.byref(mx))
                    d["clk_" + key] = f"{x.value} MHz" + (f"  (max {mx.value})" if mx.value else "")
            if g("nvmlDeviceGetPowerUsage", h, C.byref(x)):
                d["power"] = f"{x.value / 1000:.0f} W"
                if g("nvmlDeviceGetEnforcedPowerLimit", h, C.byref(x)):
                    d["power"] += f"  (limit {x.value / 1000:.0f} W)"
            if g("nvmlDeviceGetFanSpeed", h, C.byref(x)):
                d["fan"] = f"%{x.value}"
            ge, wi = C.c_uint(), C.c_uint()
            if g("nvmlDeviceGetCurrPcieLinkGeneration", h, C.byref(ge)) and g("nvmlDeviceGetCurrPcieLinkWidth", h, C.byref(wi)):
                d["pcie"] = f"Gen{ge.value} x{wi.value}"
            ma, mi = C.c_int(), C.c_int()
            if g("nvmlDeviceGetCudaComputeCapability", h, C.byref(ma), C.byref(mi)):
                d["cc"] = f"{ma.value}.{mi.value}"
            out.append(d)
    g("nvmlShutdown")
    return drv.value.decode(), out


def t_gpu():
    r = []
    cards = [c for c in sorted(glob.glob("/sys/class/drm/card*")) if c.rsplit("card", 1)[1].isdigit()]
    nvd, nv_i = None, 0
    for c in cards:
        d = c + "/device"
        try:
            v, dev = int(rd(d + "/vendor"), 16), int(rd(d + "/device"), 16)
        except ValueError:
            continue
        drv = rlink(d + "/driver")
        r.append(H(pci_name(v, dev)))
        add(r, L("PCI ID", "PCI ID"), f"{v:04x}:{dev:04x}")
        sv = rd(d + "/subsystem_vendor")
        if sv:
            try:
                s = int(sv, 16)
                pci_lookup([(s, 0)])
                add(r, L("Board vendor", "Kart üreticisi"), vshort(_IDS[(s, 0)][0]))
            except ValueError:
                pass
        add(r, L("Driver in use", "Kullanılan sürücü"), drv or L("none", "yok"), "ok" if drv else "warn")
        add(r, L("Revision", "Revizyon"), rd(d + "/revision"))
        cl, ml = rd(d + "/current_link_speed"), rd(d + "/max_link_speed")
        cw, mw = rd(d + "/current_link_width"), rd(d + "/max_link_width")
        if cl:
            add(r, "PCIe", f"{cl} x{cw}  ({L('max', 'maks')} {ml} x{mw})")
        vt = rd(d + "/mem_info_vram_total")
        if vt:
            add(r, "VRAM", f"{human(int(rd(d + '/mem_info_vram_used') or 0))} / {human(int(vt))}")
            add(r, L("GPU usage", "GPU kullanımı"), "%" + rd(d + "/gpu_busy_percent"))
        for t in glob.glob(d + "/hwmon/hwmon*/temp1_input"):
            add(r, L("Temperature", "Sıcaklık"), f"{int(rd(t)) / 1000:.0f} °C")
        fq = rd(c + "/gt_cur_freq_mhz")
        if fq:
            add(r, L("Frequency", "Frekans"), f"{fq} MHz  (max {rd(c + '/gt_max_freq_mhz')})")
        if drv == "nvidia":
            if nvd is None:
                nvd = nvml()
            ver, devs = nvd
            add(r, L("Driver version", "Sürücü sürümü"), ver)
            if nv_i < len(devs):
                n = devs[nv_i]
                nv_i += 1
                add(r, L("VRAM", "VRAM"), n.get("vram"))
                add(r, L("GPU usage", "GPU kullanımı"), n.get("util"))
                add(r, L("Temperature", "Sıcaklık"), n.get("temp"))
                add(r, L("Core clock", "Çekirdek saati"), n.get("clk_gr"))
                add(r, L("Memory clock", "Bellek saati"), n.get("clk_mem"))
                add(r, L("Power", "Güç"), n.get("power"))
                add(r, L("Fan", "Fan"), n.get("fan"))
                add(r, L("PCIe link", "PCIe bağlantısı"), n.get("pcie"))
                add(r, L("CUDA compute capability", "CUDA hesaplama yeteneği"), n.get("cc"))
            else:
                add(r, "NVML", L("not available", "kullanılamıyor"))
    return r or [note(L("No GPU found.", "Ekran kartı bulunamadı."))]


def edid_info(p):
    try:
        with open(p, "rb") as f:
            e = f.read(128)
    except Exception:
        return {}
    if len(e) < 128 or e[:8] != b"\x00\xff\xff\xff\xff\xff\xff\x00":
        return {}
    m = (e[8] << 8) | e[9]
    mf = "".join(chr(((m >> s) & 31) + 64) for s in (10, 5, 0))
    name = ""
    for o in (54, 72, 90, 108):
        if e[o:o + 3] == b"\x00\x00\x00" and e[o + 3] == 0xFC:
            name = e[o + 5:o + 18].decode("ascii", "ignore").strip()
    return {"mf": mf, "name": name, "w": e[21], "h": e[22], "year": 1990 + e[17]}


def t_disp():
    r = []
    for st in sorted(glob.glob("/sys/class/drm/card*-*/status")):
        d = os.path.dirname(st)
        if rd(st) != "connected":
            continue
        e = edid_info(d + "/edid")
        modes = rd(d + "/modes").splitlines()
        r.append(H(f"{e.get('name') or L('Display', 'Monitör')}  ·  {os.path.basename(d).split('-', 1)[1]}"))
        add(r, L("Manufacturer", "Üretici"), e.get("mf"))
        add(r, L("Preferred resolution", "Tercih edilen çözünürlük"), modes[0] if modes else "")
        add(r, L("Available modes", "Kullanılabilir mod sayısı"), len(modes))
        if e.get("w"):
            add(r, L("Physical size", "Fiziksel boyut"), f"{e['w']} × {e['h']} cm")
        add(r, L("Manufacture year", "Üretim yılı"), e.get("year"))
    return r or [note(L("No connected display detected.", "Bağlı monitör bulunamadı."))]


# ------------------------------------------------------------------- depolama
SKIP = ("loop", "ram", "zram", "dm-", "sr", "fd", "md", "nbd")


def disks():
    return [n for n in sorted(os.listdir("/sys/block")) if not n.startswith(SKIP)]


def mounts():
    m = {}
    for line in rd("/proc/mounts").splitlines():
        p = line.split()
        if len(p) >= 3 and p[0].startswith("/dev/"):
            m.setdefault(os.path.realpath(p[0]), (p[1].replace("\\040", " "), p[2]))
    return m


def iface(n):
    if n.startswith("nvme"):
        return "NVMe"
    if n.startswith("mmcblk"):
        return "eMMC / SD"
    p = os.path.realpath(f"/sys/block/{n}")
    if "/usb" in p:
        return "USB"
    if "/ata" in p:
        return "SATA"
    return "?"


ATTR = {1: "Raw Read Error Rate", 3: "Spin-Up Time", 4: "Start/Stop Count", 5: "Reallocated Sectors",
        7: "Seek Error Rate", 9: "Power-On Hours", 10: "Spin Retry Count", 12: "Power Cycle Count",
        177: "Wear Leveling Count", 181: "Program Fail Count", 182: "Erase Fail Count",
        187: "Reported Uncorrectable", 188: "Command Timeout", 190: "Airflow Temperature",
        192: "Power-Off Retract Count", 193: "Load Cycle Count", 194: "Temperature",
        196: "Reallocation Events", 197: "Current Pending Sectors", 198: "Offline Uncorrectable",
        199: "UDMA CRC Errors", 231: "SSD Life Left", 233: "Media Wearout Indicator",
        241: "Total LBAs Written", 242: "Total LBAs Read"}
HEALTH = {"ok": ("Healthy (OK)", "Sağlıklı (OK)"), "warn": ("Warning – check the details below", "Uyarı – ayrıntılara bak"),
          "bad": ("FAILING – back up your data!", "ARIZALI – verini yedekle!")}


def smart_rows(r, s):
    hl = HEALTH[s["health"]]
    add(r, L("Health", "Sağlık"), L(*hl), s["health"])
    if s["kind"] == "nvme":
        add(r, L("Temperature", "Sıcaklık"), f"{s['temp']} °C")
        add(r, L("Wear (used)", "Aşınma (kullanılan)"), f"%{s['used']}", "warn" if s["used"] >= 90 else None)
        add(r, L("Spare capacity", "Yedek kapasite"), f"%{s['spare']}  ({L('threshold', 'eşik')} %{s['spare_thr']})")
        add(r, L("Data written", "Yazılan veri"), human(s["written"], True))
        add(r, L("Data read", "Okunan veri"), human(s["read"], True))
        add(r, L("Power-on time", "Çalışma süresi"), f"{s['poh']:,} {L('h', 'sa')}  (~{s['poh'] // 24} {L('days', 'gün')})")
        add(r, L("Power cycles", "Açılış sayısı"), f"{s['cycles']:,}")
        add(r, L("Unsafe shutdowns", "Güvensiz kapanma"), s["unsafe"])
        add(r, L("Media errors", "Medya hatası"), s["merr"], "bad" if s["merr"] else None)
        return
    a = {x[0]: x for x in s["attrs"]}

    def raw(i):
        return a[i][4] if i in a else None
    if raw(9) is not None:
        add(r, L("Power-on time", "Çalışma süresi"), f"{raw(9) & 0xFFFFFFFF:,} {L('h', 'sa')}  (~{(raw(9) & 0xFFFFFFFF) // 24} {L('days', 'gün')})")
    t = raw(194) if raw(194) is not None else raw(190)
    if t is not None:
        add(r, L("Temperature", "Sıcaklık"), f"{t & 0xFF} °C")
    add(r, L("Power cycles", "Açılış sayısı"), raw(12))
    for i, lab in ((5, L("Reallocated sectors", "Yer değiştiren sektör")), (197, L("Pending sectors", "Bekleyen sektör")),
                   (198, L("Uncorrectable sectors", "Düzeltilemeyen sektör")), (199, L("Cable/CRC errors", "Kablo/CRC hatası"))):
        if raw(i) is not None:
            add(r, lab, raw(i) & 0xFFFFFFFF, "bad" if raw(i) & 0xFFFFFFFF else "ok")
    for i in (231, 233, 177):
        if i in a:
            add(r, L("SSD life left", "SSD kalan ömür"), f"%{a[i][1]}")
            break
    if raw(241) is not None:
        add(r, L("Data written", "Yazılan veri"), human((raw(241) & 0xFFFFFFFFFFFF) * 512, True))
    r.append(H(L("SMART attributes", "SMART öznitelikleri")))
    for i, v, w, th, rw in sorted(s["attrs"]):
        bad = (th and v <= th) or (i in (5, 187, 196, 197, 198) and rw & 0xFFFFFFFF)
        add(r, f"{i:3d}  {ATTR.get(i, 'Attribute ' + str(i))}",
            f"{L('value', 'değer')} {v} / {L('worst', 'en kötü')} {w} / {L('thr', 'eşik')} {th}  ·  raw {rw}", "warn" if bad else None)


def t_disk():
    r, mt = [], mounts()
    sm = ROOT.get("smart", {})
    for n in disks():
        b = f"/sys/block/{n}"
        size = int(rd(b + "/size") or 0) * 512
        model = rd(b + "/device/model") or L("Unknown", "Bilinmeyen")
        nv = n.startswith("nvme")
        kind = "HDD" if rd(b + "/queue/rotational") == "1" else ("NVMe SSD" if nv else "SSD")
        r.append(H(f"/dev/{n}  ·  {model}"))
        add(r, L("Capacity", "Kapasite"), human(size, True))
        add(r, L("Type / interface", "Tür / arayüz"), f"{kind}  ·  {iface(n)}")
        for t in glob.glob(b + "/device/hwmon*/temp1_input") + glob.glob(b + "/device/hwmon/hwmon*/temp1_input"):
            add(r, L("Temperature", "Sıcaklık"), f"{int(rd(t)) / 1000:.0f} °C")
            break
        if n in sm:
            s = sm[n]
            if "err" in s:
                add(r, L("Health", "Sağlık"), L("Could not read SMART (", "SMART okunamadı (") + s["err"] + ")", "warn")
            else:
                smart_rows(r, s)
        for p in sorted(x for x in os.listdir(b) if x.startswith(n) and os.path.exists(f"{b}/{x}/partition")):
            ps = int(rd(f"{b}/{p}/size") or 0) * 512
            mp, fs = mt.get(f"/dev/{p}", ("", ""))
            use = ""
            if mp:
                try:
                    st = os.statvfs(mp)
                    tot = st.f_blocks * st.f_frsize
                    use = f"  ·  {human(tot - st.f_bavail * st.f_frsize, True)} / {human(tot, True)}"
                except OSError:
                    pass
            add(r, f"  /dev/{p}", f"{human(ps, True)}  {fs}  {mp}{use}".strip())
    if not sm:
        r.append(note(L("Press “Unlock details” to read SMART health data (needs administrator permission).",
                        "SMART sağlık verisi için “Ayrıntıları aç” butonuna bas (yönetici izni gerekir).")))
    return r or [note(L("No disks found.", "Disk bulunamadı."))]


def t_net():
    r = []
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    import fcntl
    for n in sorted(os.listdir("/sys/class/net")):
        if n == "lo":
            continue
        b = f"/sys/class/net/{n}"
        r.append(H(f"{n}  ·  " + (L("Wi-Fi", "Kablosuz") if os.path.isdir(b + "/wireless") else L("Wired / virtual", "Kablolu / sanal"))))
        add(r, L("State", "Durum"), rd(b + "/operstate"), "ok" if rd(b + "/operstate") == "up" else None)
        add(r, "MAC", rd(b + "/address"))
        try:
            ip = socket.inet_ntoa(fcntl.ioctl(s.fileno(), 0x8915, struct.pack("256s", n[:15].encode()))[20:24])
            add(r, "IPv4", ip)
        except OSError:
            pass
        sp = rd(b + "/speed")
        if sp.lstrip("-").isdigit() and int(sp) > 0:
            add(r, L("Link speed", "Bağlantı hızı"), f"{sp} Mbit/s")
        add(r, L("Driver", "Sürücü"), rlink(b + "/device/driver"))
        add(r, L("Received / sent", "Alınan / gönderilen"),
            f"{human(int(rd(b + '/statistics/rx_bytes') or 0))} / {human(int(rd(b + '/statistics/tx_bytes') or 0))}")
    s.close()
    for line in rd("/proc/net/route").splitlines()[1:]:
        p = line.split()
        if len(p) > 2 and p[1] == "00000000":
            r.append(H(L("Gateway & DNS", "Ağ geçidi ve DNS")))
            add(r, L("Default gateway", "Varsayılan ağ geçidi"), f"{socket.inet_ntoa(struct.pack('<L', int(p[2], 16)))}  ({p[0]})")
            break
    dns = re.findall(r"^nameserver\s+(\S+)", rd("/etc/resolv.conf"), re.M)
    add(r, "DNS", ", ".join(dns))
    return r


def t_audio():
    lines = rd("/proc/asound/cards").splitlines()
    r = []
    for i, l in enumerate(lines):
        m = re.match(r"\s*(\d+)\s+\[(.*?)\s*\]:\s*(.*)", l)
        if not m:
            continue
        num = m.group(1)
        r.append(H(f"{L('Card', 'Kart')} {num}: {m.group(3)}"))
        add(r, L("Description", "Açıklama"), lines[i + 1].strip() if i + 1 < len(lines) else "")
        add(r, L("Driver", "Sürücü"), rlink(f"/sys/class/sound/card{num}/device/driver"))
        for cf in sorted(glob.glob(f"/proc/asound/card{num}/codec#*"))[:1]:
            for ln in rd(cf).splitlines()[:2]:
                if ln.startswith("Codec:"):
                    add(r, "Codec", ln.split(":", 1)[1].strip())
    return r or [note(L("No sound cards found.", "Ses kartı bulunamadı."))]


PCLS = {0x01: ("Storage", "Depolama"), 0x02: ("Network", "Ağ"), 0x03: ("Graphics", "Ekran"), 0x04: ("Multimedia", "Multimedya"),
        0x06: ("Bridge", "Köprü"), 0x07: ("Communication", "İletişim"), 0x08: ("System", "Sistem"), 0x0c: ("Serial bus / USB", "Seri veri yolu / USB"),
        0x0d: ("Wireless", "Kablosuz")}


def t_drv():
    r = []
    devs = pci_devices()
    pci_lookup([(d["v"], d["d"]) for d in devs])
    r.append(H(L("PCI devices and their drivers", "PCI aygıtları ve sürücüleri")))
    for d in devs:
        c = PCLS.get(d["cls"] >> 16)
        add(r, f"{d['addr']}  {pci_name(d['v'], d['d'])}", (d["drv"] or L("(no driver)", "(sürücü yok)")) + (f"   [{L(*c)}]" if c else ""),
            None if d["drv"] else "warn")
    usb = []
    for p in sorted(glob.glob("/sys/bus/usb/devices/*:*")):
        drv = rlink(p + "/driver")
        if not drv or drv == "hub":
            continue
        dv = "/sys/bus/usb/devices/" + os.path.basename(p).split(":")[0]
        nm = f"{rd(dv + '/manufacturer')} {rd(dv + '/product')}".strip() or rd(dv + "/idVendor") + ":" + rd(dv + "/idProduct")
        usb.append((nm, drv))
    if usb:
        r.append(H(L("USB devices and their drivers", "USB aygıtları ve sürücüleri")))
        for nm, drv in usb:
            add(r, nm, drv)
    mods = []
    for line in rd("/proc/modules").splitlines():
        p = line.split()
        if len(p) >= 4:
            mods.append((p[0], int(p[1]), p[3].strip(",")))
    mods.sort()
    r.append(H(f"{L('Loaded kernel modules', 'Yüklü çekirdek modülleri')} ({len(mods)})"))
    for n, sz, by in mods:
        add(r, n, human(sz) + (f"   ←  {by}" if by and by != "-" else ""))
    return r


def t_sens():
    r = []
    for h in sorted(glob.glob("/sys/class/hwmon/hwmon*")):
        sub = []
        for t in sorted(glob.glob(h + "/temp*_input")):
            v = rd(t)
            if v.lstrip("-").isdigit():
                sub.append((rd(t.replace("_input", "_label")) or os.path.basename(t).split("_")[0], f"{int(v) / 1000:.1f} °C"))
        for f in sorted(glob.glob(h + "/fan*_input")):
            sub.append((os.path.basename(f).split("_")[0], f"{rd(f)} RPM"))
        for v in sorted(glob.glob(h + "/in*_input")):
            x = rd(v)
            if x.lstrip("-").isdigit():
                sub.append((rd(v.replace("_input", "_label")) or os.path.basename(v).split("_")[0], f"{int(x) / 1000:.3f} V"))
        if sub:
            r.append(H(rd(h + "/name") or os.path.basename(h)))
            r += [(a, b, None) for a, b in sub]
    for ps in sorted(glob.glob("/sys/class/power_supply/*")):
        if rd(ps + "/type") == "Battery":
            r.append(H(L("Battery", "Pil")))
            add(r, L("Charge", "Doluluk"), "%" + rd(ps + "/capacity"))
            add(r, L("Status", "Durum"), rd(ps + "/status"))
    la = rd("/proc/loadavg").split()[:3]
    if la:
        r.append(H(L("Load", "Yük")))
        add(r, L("Load average (1/5/15 min)", "Yük ortalaması (1/5/15 dk)"), " / ".join(la))
    return r or [note(L("No sensors found.", "Sensör bulunamadı."))]


TABS = [("sys", "System", "Sistem", t_system), ("cpu", "Processor", "İşlemci", t_cpu), ("mem", "Memory", "Bellek", t_mem),
        ("board", "Motherboard & BIOS", "Anakart & BIOS", t_board), ("gpu", "Graphics", "Ekran Kartı", t_gpu),
        ("disp", "Displays", "Monitörler", t_disp), ("disk", "Storage & Health", "Depolama & Sağlık", t_disk),
        ("net", "Network", "Ağ", t_net), ("audio", "Audio", "Ses", t_audio), ("drv", "Drivers", "Sürücüler", t_drv),
        ("sens", "Sensors", "Sensörler", t_sens)]
LIVE = ("cpu", "sens")
NEEDS_ROOT = ("mem", "disk")

#root
def smart_nvme(n):
    import ctypes as C
    m = re.match(r"(nvme\d+)", n)
    fd = os.open("/dev/" + m.group(1), os.O_RDONLY | os.O_NONBLOCK)
    try:
        buf = C.create_string_buffer(512)
        cmd = C.create_string_buffer(struct.pack("<BBH3I2Q2I6I2I", 0x02, 0, 0, 0xFFFFFFFF, 0, 0, 0, C.addressof(buf), 0, 512,
                                                 (127 << 16) | 0x02, 0, 0, 0, 0, 0, 0, 0))
        if C.CDLL(None, use_errno=True).ioctl(fd, 0xC0484E41, cmd) != 0:
            raise OSError("NVMe ioctl")
    finally:
        os.close(fd)
    b = buf.raw
    le = lambda a, z: int.from_bytes(b[a:z], "little")
    s = {"kind": "nvme", "crit": b[0], "temp": le(1, 3) - 273, "spare": b[3], "spare_thr": b[4], "used": b[5],
         "read": le(32, 48) * 512000, "written": le(48, 64) * 512000, "cycles": le(112, 128), "poh": le(128, 144),
         "unsafe": le(144, 160), "merr": le(160, 176)}
    s["health"] = "bad" if s["crit"] else "warn" if (s["used"] >= 90 or s["spare"] <= s["spare_thr"] or s["merr"]) else "ok"
    return s


def _ata(fd, feat):
    import ctypes as C

    class Sg(C.Structure):
        _fields_ = [("interface_id", C.c_int), ("dxfer_direction", C.c_int), ("cmd_len", C.c_ubyte), ("mx_sb_len", C.c_ubyte),
                    ("iovec_count", C.c_ushort), ("dxfer_len", C.c_uint), ("dxferp", C.c_void_p), ("cmdp", C.c_void_p),
                    ("sbp", C.c_void_p), ("timeout", C.c_uint), ("flags", C.c_uint), ("pack_id", C.c_int),
                    ("usr_ptr", C.c_void_p), ("status", C.c_ubyte), ("masked_status", C.c_ubyte), ("msg_status", C.c_ubyte),
                    ("sb_len_wr", C.c_ubyte), ("host_status", C.c_ushort), ("driver_status", C.c_ushort),
                    ("resid", C.c_int), ("duration", C.c_uint), ("info", C.c_uint)]
    buf, sense = C.create_string_buffer(512), C.create_string_buffer(32)
    cdb = (C.c_ubyte * 16)(0x85, 0x08, 0x0E, 0, feat, 0, 1, 0, 0, 0, 0x4F, 0, 0xC2, 0, 0xB0, 0)
    h = Sg()
    h.interface_id, h.dxfer_direction, h.cmd_len, h.mx_sb_len, h.dxfer_len = ord("S"), -3, 16, 32, 512
    h.dxferp, h.cmdp, h.sbp, h.timeout = C.addressof(buf), C.addressof(cdb), C.addressof(sense), 10000
    if C.CDLL(None, use_errno=True).ioctl(fd, 0x2285, C.byref(h)) != 0 or h.status != 0 or h.host_status != 0:
        raise OSError("SMART ioctl")
    return buf.raw


def smart_ata(n):
    fd = os.open("/dev/" + n, os.O_RDONLY | os.O_NONBLOCK)
    try:
        d = _ata(fd, 0xD0)
        th = {}
        try:
            t = _ata(fd, 0xD1)
            for i in range(30):
                o = 2 + i * 12
                if t[o]:
                    th[t[o]] = t[o + 1]
        except OSError:
            pass
    finally:
        os.close(fd)
    attrs, bad, warn = [], False, False
    for i in range(30):
        o = 2 + i * 12
        if not d[o]:
            continue
        aid, val, worst, raw = d[o], d[o + 3], d[o + 4], int.from_bytes(d[o + 5:o + 11], "little")
        thr = th.get(aid, 0)
        attrs.append([aid, val, worst, thr, raw])
        if d[o + 1] & 1 and thr and val <= thr:
            bad = True
        if aid in (5, 187, 196, 197, 198) and raw & 0xFFFFFFFF:
            warn = True
    return {"kind": "ata", "attrs": attrs, "health": "bad" if bad else "warn" if warn else "ok"}


def dmi_ram():
    types = {0x12: "DDR", 0x13: "DDR2", 0x18: "DDR3", 0x1A: "DDR4", 0x1E: "LPDDR4", 0x22: "DDR5", 0x23: "LPDDR5"}
    forms = {9: "DIMM", 0xC: "RIMM", 0xD: "SODIMM", 0xF: "FB-DIMM"}
    out = []
    for p in sorted(glob.glob("/sys/firmware/dmi/entries/17-*/raw")):
        with open(p, "rb") as f:
            b = f.read()
        ln = b[1]
        if ln < 0x1B:
            continue
        strs = b[ln:].split(b"\0")
        S = lambda i: strs[i - 1].decode("ascii", "ignore").strip() if 0 < i <= len(strs) else ""
        w = struct.unpack_from("<H", b, 0x0C)[0]
        if w == 0:
            continue
        if w == 0x7FFF and ln >= 0x20:
            mib = struct.unpack_from("<I", b, 0x1C)[0]
        elif w & 0x8000:
            mib = (w & 0x7FFF) // 1024
        else:
            mib = w
        out.append({"loc": S(b[0x10]), "mib": mib, "type": types.get(b[0x12], ""), "form": forms.get(b[0x0E], ""),
                    "speed": struct.unpack_from("<H", b, 0x15)[0] if ln >= 0x17 else 0,
                    "cfg": struct.unpack_from("<H", b, 0x20)[0] if ln >= 0x22 else 0,
                    "mfr": S(b[0x17]), "part": S(b[0x1A])})
    return out


def root_collect():
    out = {"smart": {}, "ram": []}
    for n in disks():
        try:
            out["smart"][n] = smart_nvme(n) if n.startswith("nvme") else smart_ata(n)
        except Exception as e:
            out["smart"][n] = {"err": str(e)}
    try:
        out["ram"] = dmi_ram()
    except Exception:
        pass
    return out


# ------------------------------------------------------------------------------ GUI
BG, SIDE, SEL, HOV = "#0f1217", "#141821", "#1c2433", "#181e2a"
FG, DIM, ACC = "#e6e9f0", "#8a93a5", "#5b9cff"
COL = {"ok": "#4ade80", "warn": "#fbbf24", "bad": "#f87171"}


def main():
    global LANG
    import tkinter as tk
    from tkinter import ttk, font as tkfont

    LANG = detect_lang()
    root = tk.Tk()
    root.geometry("1040x660")
    root.minsize(820, 520)
    root.configure(bg=BG)
    base = tkfont.nametofont("TkDefaultFont").actual()["family"]
    f_norm, f_bold = (base, 10), (base, 10, "bold")
    f_title = (base, 17, "bold")

    st = {"cur": "sys", "busy": False, "proc": None}
    side = tk.Frame(root, bg=SIDE, width=220)
    side.pack(side="left", fill="y")
    side.pack_propagate(False)
    tk.Label(side, text="Hardware Info", bg=SIDE, fg=ACC, font=(base, 14, "bold"), anchor="w", padx=18, pady=18).pack(fill="x")

    items = {}

    def paint():
        for k, (row, bar, lbl) in items.items():
            on = k == st["cur"]
            for w in (row, lbl):
                w.configure(bg=SEL if on else SIDE)
            bar.configure(bg=ACC if on else SIDE)
            lbl.configure(fg=FG if on else DIM)

    def hover(k, on):
        if k != st["cur"]:
            for w in items[k][::2]:
                w.configure(bg=HOV if on else SIDE)

    for key, en, tr, fn in TABS:
        row = tk.Frame(side, bg=SIDE, cursor="hand2")
        row.pack(fill="x")
        bar = tk.Frame(row, width=3, bg=SIDE)
        bar.pack(side="left", fill="y")
        lbl = tk.Label(row, bg=SIDE, fg=DIM, anchor="w", padx=14, pady=9, font=f_norm)
        lbl.pack(side="left", fill="x", expand=True)
        items[key] = (row, bar, lbl)
        for w in (row, lbl):
            w.bind("<Button-1>", lambda e, k=key: show(k))
            w.bind("<Enter>", lambda e, k=key: hover(k, True))
            w.bind("<Leave>", lambda e, k=key: hover(k, False))

    foot = tk.Frame(side, bg=SIDE)
    foot.pack(side="bottom", fill="x", pady=10, padx=14)
    langs = tk.Frame(foot, bg=SIDE)
    langs.pack(side="bottom", anchor="w")
    lang_lbl = {}

    def set_lang(code):
        global LANG
        LANG = code
        relabel()
        show(st["cur"])

    for code in ("en", "tr"):
        lb = tk.Label(langs, text=code.upper(), bg=SIDE, font=f_bold, cursor="hand2", padx=6)
        lb.pack(side="left")
        lb.bind("<Button-1>", lambda e, c=code: set_lang(c))
        lang_lbl[code] = lb

    main_f = tk.Frame(root, bg=BG)
    main_f.pack(side="left", fill="both", expand=True)
    head = tk.Frame(main_f, bg=BG)
    head.pack(fill="x", padx=26, pady=(20, 4))
    title = tk.Label(head, bg=BG, fg=FG, font=f_title, anchor="w")
    title.pack(side="left")

    def button(parent, cmd):
        b = tk.Label(parent, bg="#1d2431", fg=FG, font=f_norm, padx=12, pady=5, cursor="hand2")
        b.bind("<Button-1>", lambda e: cmd())
        b.bind("<Enter>", lambda e: b.configure(bg="#27314a"))
        b.bind("<Leave>", lambda e: b.configure(bg="#1d2431"))
        return b

    refresh_b = button(head, lambda: show(st["cur"]))
    refresh_b.pack(side="right")
    unlock_b = button(head, lambda: unlock())
    status = tk.Label(head, bg=BG, fg=DIM, font=f_norm)
    status.pack(side="right", padx=10)

    body = tk.Frame(main_f, bg=BG)
    body.pack(fill="both", expand=True)
    style = ttk.Style()
    style.theme_use("clam")
    style.layout("D.Vertical.TScrollbar", [("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [
        ("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]})])
    style.configure("D.Vertical.TScrollbar", background="#2a3242", troughcolor=BG, bordercolor=BG, lightcolor="#2a3242",
                    darkcolor="#2a3242", gripcount=0, width=10)
    style.map("D.Vertical.TScrollbar", background=[("active", "#3a4560")])
    sb = ttk.Scrollbar(body, style="D.Vertical.TScrollbar", orient="vertical")
    sb.pack(side="right", fill="y", pady=(0, 8))
    text = tk.Text(body, bg=BG, fg=FG, font=f_norm, relief="flat", bd=0, highlightthickness=0, wrap="word", padx=26, pady=4,
                   insertwidth=0, cursor="arrow", selectbackground="#2b3f66", selectforeground=FG, spacing1=3, spacing3=3,
                   yscrollcommand=sb.set, tabs=("300",))
    text.pack(side="left", fill="both", expand=True)
    sb.configure(command=text.yview)
    text.tag_configure("h", foreground=ACC, font=(base, 11, "bold"), spacing1=20, spacing3=6)
    text.tag_configure("row", lmargin1=0, lmargin2=300)
    text.tag_configure("k", foreground=DIM)
    text.tag_configure("v", foreground=FG)
    text.tag_configure("note", foreground=DIM, font=(base, 10, "italic"), spacing1=14)
    for k, c in COL.items():
        text.tag_configure(k, foreground=c)

    def relabel():
        for key, en, tr, fn in TABS:
            items[key][2].configure(text=L(en, tr))
        for c, lb in lang_lbl.items():
            lb.configure(fg=ACC if c == LANG else DIM)
        refresh_b.configure(text=L("Refresh", "Yenile"))
        unlock_b.configure(text=L("Unlock details (root)", "Ayrıntıları aç (root)"))
        root.title(L("Hardware Info", "Donanım Bilgisi"))

    def render(rows, keep=False):
        y = text.yview()[0] if keep else 0
        text.configure(state="normal")
        text.delete("1.0", "end")
        for k, v, s in rows:
            if v is None:
                text.insert("end", k + "\n", "h")
            elif k == "":
                text.insert("end", v + "\n", s or "note")
            else:
                text.insert("end", k + "\t", ("row", "k"))
                text.insert("end", v + "\n", ("row", "v", s) if s else ("row", "v"))
        text.configure(state="disabled")
        text.yview_moveto(y)

    def collect():
        fn = [t[3] for t in TABS if t[0] == st["cur"]][0]
        try:
            return fn()
        except Exception as e:
            return [H(L("Error", "Hata")), note(str(e))]

    def show(key):
        st["cur"] = key
        paint()
        title.configure(text=[L(t[1], t[2]) for t in TABS if t[0] == key][0])
        if key in NEEDS_ROOT and not ROOT:
            unlock_b.pack(side="right", padx=(0, 8))
        else:
            unlock_b.pack_forget()
        render(collect())
        gc.collect()

    def finish(msg=""):
        st["busy"] = False
        status.configure(text=msg)
        show(st["cur"])

    def poll():
        p = st["proc"]
        if p.poll() is None:
            root.after(200, poll)
            return
        try:
            ROOT.update(json.loads(p.stdout.read()))
            finish()
        except Exception:
            finish(L("Authorization failed or cancelled", "Yetkilendirme başarısız veya iptal edildi"))

    def unlock():
        if st["busy"]:
            return
        st["busy"] = True
        if os.geteuid() == 0:
            ROOT.update(root_collect())
            return finish()
        status.configure(text=L("Waiting for authorization…", "Yetki bekleniyor…"))
        cmd = ["pkexec", sys.executable] + ([] if getattr(sys, "frozen", False) else [os.path.abspath(__file__)]) + ["--root"]
        try:
            st["proc"] = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        except OSError:
            return finish(L("pkexec not found – run the program with sudo", "pkexec bulunamadı – programı sudo ile çalıştır"))
        root.after(200, poll)

    def tick():
        if st["cur"] in LIVE and root.state() == "normal" and not st["busy"]:
            render(collect(), keep=True)
        root.after(2000, tick)

    relabel()
    show("sys")
    root.after(2000, tick)
    root.mainloop()


if __name__ == "__main__":
    if "--root" in sys.argv:
        sys.stdout.write(json.dumps(root_collect()))
    else:
        main()
