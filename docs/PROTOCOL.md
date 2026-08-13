# Danfoss Eco (eTRV) BLE Protocol Reference

Everything this integration knows about the Danfoss Eco 2 (tested on 014G1001)
Bluetooth protocol, collected from the MIT-licensed prior art
([libetrv](https://github.com/AdamStrojek/libetrv),
[etrv2mqtt](https://github.com/keton/etrv2mqtt),
[esphome-danfoss-eco](https://github.com/dmitry-cherkas/esphome-danfoss-eco))
and verified against real hardware in August 2026.

## Advertisements

The device advertises continuously as a connectable BLE peripheral:

- **MAC OUI**: `00:04:2F` (Danfoss)
- **Local name**: `<digit>;<mac-without-leading-zero>;eTRV`, e.g.
  `0;0:04:2F:80:BB:16;eTRV`
- The **leading digit is live device state**, observed values `0/2/4/6`.
  `6` appears right after the timer button is pressed (pairing window open).
  The exact semantics of the other values are unknown (possibly a counter of
  connection/auth events).
- No service UUIDs are advertised — discovery must match on the local name or
  the OUI.

## GATT layout

### Settings service `10020000-2749-0001-0000-00805f9b042f`

| Characteristic | UUID (`100200xx-2749-0001-0000-00805f9b042f`) | Handle¹ | Access | Content (decrypted) |
|---|---|---|---|---|
| PIN | `...01` | 0x24 | write | `uint32 BE` PIN code, **plaintext** (not XXTEA) |
| Settings | `...03` | 0x2A | read/write | 16 B settings block (below) |
| Temperature | `...05` | 0x2D | read/write | 8 B: `[0]` setpoint, `[1]` room temp (both ×0.5 °C); write back the full block with `[0]` changed |
| Name | `...06` | 0x30 | read/write | device name, UTF-8, NUL-padded |
| Current time | `...08` | — | read/write | `int32 BE` local epoch (UTC + offset), `int32 BE` UTC-offset seconds |
| Errors | `...09` | 0x39 | read | 8 B: `uint16 BE` flags at offset 0 (below) |
| **Secret key** | `...0b` | 0x3F | read | 16 B raw key — **characteristic only exists in the GATT table while the pairing window is open** |

¹ handles from libetrv; this integration addresses by UUID only.

### Battery service (standard)

`0x180F` / characteristic `0x2A19` — battery percent, single byte, **not encrypted**.

## Encryption

Every settings-service characteristic except