# -*- coding: utf-8 -*-
"""Swell / shrinkage and mass-haul helpers (Plan 07 M4, ROADGEN handbook #m4)."""

# Handbook SWELL / SHRINK (ROADGEN_ultimate_pipeline_v2.html #m4)
SWELL = {
    'ordinary_soil': 1.25,
    'soft_rock': 1.15,
    'hard_rock': 1.35,
    'loose_rock': 1.30,
    'murrum': 1.10,
    'moorum': 1.12,
}
SHRINK = {
    'ordinary_soil': 0.90,
    'soft_rock': 0.88,
    'loose_rock': 0.85,
    'murrum': 0.92,
    'moorum': 0.92,
    # hard_rock: no shrink in handbook card — use 1.0 (no borrow inflation)
}

VALID_SOIL_TYPES = tuple(SWELL.keys())


def factors_for_soil(soil_type):
    key = (soil_type or 'ordinary_soil').strip().lower().replace(' ', '_')
    if key not in SWELL:
        key = 'ordinary_soil'
    swell = SWELL[key]
    shrink = SHRINK.get(key, 1.0)
    return {'swell_cut': swell, 'shrink_fill': shrink, 'soil_type': key}


def apply_swell_shrink(cut_m3, fill_m3, soil_type):
    """
    Handbook: cut_haul = cut_bank * swell; fill_borrow = fill_comp / shrink;
    borrow_req = max(0, -net_surplus); spoil = max(0, net_surplus).
    """
    f = factors_for_soil(soil_type)
    cut_bank = float(cut_m3)
    fill_comp = float(fill_m3)
    swell_f = f['swell_cut']
    shrink_f = f['shrink_fill']
    cut_haul = cut_bank * swell_f
    fill_borrow = fill_comp / shrink_f if shrink_f else fill_comp
    net_haul = cut_haul - fill_borrow
    borrow_req = max(0.0, -net_haul)
    spoil_m3 = max(0.0, net_haul)
    soil = f['soil_type']
    return {
        'cut_m3': cut_bank,
        'fill_m3': fill_comp,
        'cut_bank_m3': cut_bank,
        'fill_comp_m3': fill_comp,
        'cut_haul_m3': cut_haul,
        'cut_loose_m3': cut_haul,
        'fill_borrow_m3': fill_borrow,
        'fill_compacted_m3': fill_comp,
        'net_haul_m3': net_haul,
        'borrow_req_m3': borrow_req,
        'spoil_m3': spoil_m3,
        'swell_factor': swell_f,
        'shrink_factor': shrink_f,
        'soil_type': soil,
    }


def allocate_region_volumes(total_cut, total_fill, regions):
    """Split corridor totals by region chainage length (MVP when per-region Civil API unavailable)."""
    if not regions:
        return []
    lengths = []
    for r in regions:
        s0 = float(r.get('start_sta', 0) or 0)
        s1 = float(r.get('end_sta', 0) or 0)
        lengths.append(max(0.0, s1 - s0))
    total_len = sum(lengths) or 1.0
    out = []
    for r, length in zip(regions, lengths):
        frac = length / total_len
        out.append({
            'region_name': (r.get('region_id') or '').strip(),
            'station_from': float(r.get('start_sta', 0) or 0),
            'station_to': float(r.get('end_sta', 0) or 0),
            'assembly_name': (r.get('assembly_name') or '').strip(),
            'cut_m3': total_cut * frac,
            'fill_m3': total_fill * frac,
        })
    return out


def mass_haul_ordinates(
    cut_haul_m3,
    fill_borrow_m3,
    interval_m=20.0,
    length_m=1000.0,
):
    """
    Simplified mass-haul ordinate table (uniform cut/fill along alignment).
    Returns rows + summary dict (economic lead, assumptions).
    """
    interval_m = float(interval_m or 20.0)
    length_m = float(length_m or 1000.0)
    n = max(1, int(round(length_m / interval_m)))
    cut_per = float(cut_haul_m3) / n
    fill_per = float(fill_borrow_m3) / n
    rows = []
    cumulative = 0.0
    for i in range(n + 1):
        sta = min(i * interval_m, length_m)
        if i > 0:
            cumulative += cut_per - fill_per
        ordinate = cumulative
        if ordinate > 0.001:
            haul_dir = 'export'
        elif ordinate < -0.001:
            haul_dir = 'import'
        else:
            haul_dir = 'balance'
        rows.append({
            'station_m': sta,
            'ordinate_m3': ordinate,
            'haul_direction': haul_dir,
            'cumulative_volume': ordinate,
            'cut_ordinate_m3': cut_per * i,
            'fill_ordinate_m3': fill_per * i,
            'net_ordinate_m3': ordinate,
        })
    imbalance = abs(float(cut_haul_m3) - float(fill_borrow_m3))
    denom = max(float(cut_haul_m3), float(fill_borrow_m3), 1.0)
    economic_lead_m = (imbalance / denom) * length_m * 0.5
    meta = {
        'economic_lead_m': economic_lead_m,
        'interval_m': interval_m,
        'length_m': length_m,
        'sample_count': len(rows),
        'method': 'uniform_distribution_along_alignment',
        'assumptions': (
            'Cut and fill haul/borrow volumes spread evenly by chainage; '
            'not from Civil sample lines. Replace when SampleLineGroup API is wired.'
        ),
    }
    return rows, meta


def fill_depth_from_mass_haul(rows, nominal_embankment_width_m=10.0):
    """
    MVP fill depth per station for M5 guardrail (fill > 3 m).
    fill_depth_m ≈ max(0, -net_ordinate) / nominal width.
    """
    width = float(nominal_embankment_width_m or 10.0)
    out = []
    max_fill = 0.0
    for r in rows:
        sta = float(r.get('station_m', 0) or 0)
        net = float(r.get('net_ordinate_m3', r.get('ordinate_m3', 0)) or 0)
        fill_depth = max(0.0, -net) / width if width > 0 else 0.0
        max_fill = max(max_fill, fill_depth)
        out.append({
            'station_m': sta,
            'fill_depth_m': fill_depth,
            'max_fill_height_m': fill_depth,
        })
    return out, max_fill
