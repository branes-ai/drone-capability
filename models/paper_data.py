"""Reference values from Bauersfeld & Scaramuzza, RA-L 2022 (arXiv:2109.04741).

These are the values the paper prints. The Phase 0 regression tests check
models/pen_and_paper.py against them.
"""

# Sec. VII-E worked example, DJI Mavic 3 (full precision in the paper).
MAVIC3_EXAMPLE = {
    "inputs": dict(m=0.90, r=0.119, n_rotors=4, n_series=4, capacity_ah=5.0, area_cm2=215),
    "v_ih": 4.51,      # m/s, step 1
    "p_h": 73.5,       # W, step 1
    "p_e": 67.2,       # W, step 2
    "p_r": 80.2,       # W, step 2
    "p_mot_e": 89.5,   # W, step 3
    "p_mot_r": 107.0,  # W, step 3
    "p_cell_e": 4.48,  # W/Ah, step 4
    "p_cell_r": 5.35,  # W/Ah, step 4
    "c_eff_e": 4.89,   # Ah, step 5
    "c_eff_r": 4.88,   # Ah, step 5
    "t_e": 2909,       # s, step 6
    "t_r": 2429,       # s, step 6
    "v_e": 7.75,       # m/s, step 7
    "v_r": 13.12,      # m/s, step 7
    "x_r": 32.1e3,     # m, step 8
}

# Table III. Inputs as printed: mass [kg], rotor count x propeller radius [cm],
# LiPo configuration and total capacity [Ah], surface area [cm^2].
# "paper": the paper's pen-and-paper estimates, rounded as printed:
#   endurance [min], range [km], range speed [km/h].
# "spec": manufacturer specification, or None where the paper lists none:
#   endurance [min], range [km].
TABLE_III = [
    dict(name="DJI Mavic 2", m=0.91, n_rotors=4, r=0.110, n_series=4, n_parallel=1, capacity_ah=3.9, area_cm2=200,
         paper=dict(t_e_min=33, x_r_km=24, v_r_kmh=51), spec=dict(t_min=31, x_km=18)),
    dict(name="DJI Mavic 3", m=0.90, n_rotors=4, r=0.119, n_series=4, n_parallel=1, capacity_ah=5.0, area_cm2=215,
         paper=dict(t_e_min=48, x_r_km=32, v_r_kmh=48), spec=dict(t_min=46, x_km=30)),
    dict(name="DJI Matrice 200", m=6.14, n_rotors=4, r=0.216, n_series=6, n_parallel=2, capacity_ah=15.3, area_cm2=1700,
         paper=dict(t_e_min=23, x_r_km=6.2, v_r_kmh=19), spec=dict(t_min=24, x_km=None)),
    dict(name="DJI Matrice 600 Pro", m=15.5, n_rotors=6, r=0.267, n_series=6, n_parallel=6, capacity_ah=34.2, area_cm2=1760,
         paper=dict(t_e_min=18, x_r_km=5.4, v_r_kmh=20), spec=dict(t_min=18, x_km=None)),
    dict(name="Parrot Anafi AI", m=0.90, n_rotors=4, r=0.057, n_series=4, n_parallel=1, capacity_ah=6.8, area_cm2=400,
         paper=dict(t_e_min=31, x_r_km=23, v_r_kmh=53), spec=dict(t_min=32, x_km=23)),
    dict(name="Skydio 2", m=0.78, n_rotors=4, r=0.085, n_series=3, n_parallel=1, capacity_ah=4.3, area_cm2=268,
         paper=dict(t_e_min=26, x_r_km=18, v_r_kmh=49), spec=dict(t_min=23, x_km=None)),
]


def inputs(row):
    """The keyword arguments estimate() takes, from a TABLE_III row."""
    keys = ("m", "r", "n_rotors", "n_series", "capacity_ah", "area_cm2")
    return {k: row[k] for k in keys}
