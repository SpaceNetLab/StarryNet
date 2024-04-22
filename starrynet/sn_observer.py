#encoding: utf-8
import os
import datetime
import glob
import numpy as np
from sgp4.api import Satrec, WGS84
from skyfield.api import load, wgs84, EarthSatellite


def _isl_grid(sat_cbf_t_shell):
    # [[[[ [isl] for every satellite] for every orbit] for every t] for every shell]
    isls_t_shell = []
    isl_offset = 0
    for sat_cbf_t in sat_cbf_t_shell:
        orbit_num, sat_num = sat_cbf_t.shape[1], sat_cbf_t.shape[2]
        down_cbf_t = np.roll(sat_cbf_t, -1, 2)
        right_cbf_t = np.roll(sat_cbf_t, -1, 1)
        delay_down_t = np.sqrt(np.sum(np.square(sat_cbf_t - down_cbf_t), -1)) / (
            17.31 / 29.5 * 299792.458) * 1000  # ms
        delay_right_t = np.sqrt(np.sum(np.square(sat_cbf_t - right_cbf_t), -1)) / (
            17.31 / 29.5 * 299792.458) * 1000  # ms
        isls_t = []
        for delay_down, delay_right in zip(delay_down_t, delay_right_t):
            orbit_lst = []
            idx = isl_offset
            for oid in range(orbit_num):
                sat_lst = []
                for sid in range(sat_num):
                    sat_lst.append([
                        # (isl_idx, orbit_id, sat_id, delay in ms)
                        # down isl
                        (idx, oid, sid + 1 if sid + 1 < sat_num else 0,
                         delay_down[oid, sid]),
                        # right isl
                        (idx + 1, oid + 1 if oid + 1 < orbit_num else 0, sid,
                         delay_right[oid, sid]),
                    ])
                    idx += 2
                orbit_lst.append(sat_lst)
            isls_t.append(orbit_lst)
        isl_offset += orbit_num * sat_num * 2
        isls_t_shell.append(isls_t)
    return isls_t_shell

def _gsl_least_delay(sat_cbf_t_shell, gs_cbf, antenna_num, bound_dis):
    gsls_t_shell = [] # [[[ [gsl] for every gs] for every ts] for every shell]
    for sat_cbf_t in sat_cbf_t_shell:
        gsls_t = []
        for sat_cbf in sat_cbf_t:
            orbit_num, sat_num = sat_cbf.shape[0], sat_cbf.shape[1]
            # (gs_num) op (orbit_num, sat_num) -> (gs_num, orbit_num, sat_num)
            dx = np.subtract.outer(gs_cbf[..., 0], sat_cbf[..., 0])
            dy = np.subtract.outer(gs_cbf[..., 1], sat_cbf[..., 1])
            dz = np.subtract.outer(gs_cbf[..., 2], sat_cbf[..., 2])
            dist = np.sqrt(np.square(dx) + np.square(dy) + np.square(dz))
            gsls = []
            for gs_dist in dist:
                gs_dist = gs_dist.flatten()
                bound_mask = gs_dist < bound_dis
                sat_indices = np.arange(len(gs_dist))[bound_mask]
                gs_dist = gs_dist[bound_mask]
                sorted_sat = gs_dist.argsort()
                gsls.append([
                    # (orbit_id, sat_id, delay in ms)
                    (sat_indices[sat] // sat_num, sat_indices[sat] % sat_num,
                    gs_dist[sat] / (17.31 / 29.5 * 299792.458) * 1000)
                    for sat in sorted_sat[:antenna_num]
                ])
            gsls_t.append(gsls)
        gsls_t_shell.append(gsls_t)
    
    # merge different shell
    # [[gsls for every shell] for every gs] for every t]
    gsl_shell_gs_t = [
        [list() for gid in range(len(gs_cbf))] for t in range(len(gsls_t_shell[0]))
    ]
    gsl_idx_dict = {}
    for t, gsl_shell_gs in enumerate(gsl_shell_gs_t):
        for gid, gsl_lst in enumerate(gsl_shell_gs):
            for shell_id in range(len(gsls_t_shell)):
                for oid, sid, delay in gsls_t_shell[shell_id][t][gid]:
                    if len(gsl_lst) >= antenna_num:
                        break
                    if (gid, shell_id, oid, sid) in gsl_idx_dict:
                        idx = gsl_idx_dict[(gid, shell_id, oid, sid)]
                    else:
                        idx = len(gsl_idx_dict)
                        gsl_idx_dict[(gid, shell_id, oid, sid)] = idx
                    gsl_lst.append((idx, shell_id, oid, sid, delay))
    return gsl_shell_gs_t

#TODO: More ISL styles
isl_styles = {
    'Grid': _isl_grid,
}
#TODO: More GSL styles
gsl_styles = {
    'LeastDelay':_gsl_least_delay,
}

def to_cbf(lat_long):# the xyz coordinate system.
    lat_long = np.array(lat_long)
    radius = 6371
    if lat_long.shape[-1] > 2:
        radius += lat_long[..., 2]
    theta_mat = np.radians(lat_long[..., 0])
    phi_mat = np.radians(lat_long[..., 1])
    z_mat = radius * np.sin(theta_mat)
    rho_mat = radius * np.cos(theta_mat)
    x_mat = rho_mat * np.cos(phi_mat)
    y_mat = rho_mat * np.sin(phi_mat)
    return np.stack((x_mat, y_mat, z_mat), -1)

def _bound_gsl(antenna_elevation, altitude):
    a = 6371 * np.cos(np.radians(90 + antenna_elevation))
    return a + np.sqrt(np.square(a) + np.square(altitude) + 2 * altitude * 6371)

def calculate_delay(
    dir, duration, step, shell_lst, isl_style,
    GS_lat_long, antenna_number, antenna_elevation, gsl_style
    ):
    ts_total = int(duration / step)
    cached = True
    for shell in shell_lst:
        pos_dir = os.path.join(dir, shell['name'], 'position')
        os.makedirs(pos_dir, exist_ok=True)
        if len(glob.glob(os.path.join(pos_dir, '*.txt'))) != ts_total:
            cached = False
        os.makedirs(os.path.join(dir, shell['name'], 'isl'), exist_ok=True)
        for file in glob.glob(os.path.join(dir, shell['name'], 'isl', '*.txt')):
            os.remove(file)
    gsl_dir = os.path.join(dir, 'GS-' + str(len(GS_lat_long)), 'gsl')
    os.makedirs(gsl_dir, exist_ok=True)    
    for file in glob.glob(os.path.join(gsl_dir, '*.txt')):
        os.remove(file)

    sat_cbf_t_shell = []
    if cached and input(f"Use cached local files [y/n]?").strip().lower()[:1] == 'y':
        for shell in shell_lst:
            orbit_number, sat_number = shell['orbit'], shell['sat']
            sat_lla_t = np.zeros((ts_total, orbit_number, sat_number, 3))
            pos_dir = os.path.join(dir, shell['name'], 'position')
            for t in range(ts_total):
                f = open(os.path.join(pos_dir, '%d.txt' % (t + 1)), 'r')
                for oid in range(orbit_number):
                    for sid in range(sat_number):
                        sat_lla_t[t,oid,sid]=list(map(float, f.readline().split(',')))
                    f.readline()
                f.close()
            sat_cbf_t_shell.append(to_cbf(sat_lla_t))
    else:
        for shell in shell_lst:
            for file in glob.glob(os.path.join(dir, shell['name'], 'position', '*.txt')):
                os.remove(file)

        ts = load.timescale()
        since = datetime.datetime(1949, 12, 31, 0, 0, 0)
        start = datetime.datetime(2020, 1, 1, 0, 0, 0)
        epoch = (start - since).days
        GM = 3.9860044e14
        R = 6371393
        F = 18
        ts_lst = [i * step for i in range(ts_total)]
        for i, shell in enumerate(shell_lst):        
            inclination = shell['inclination'] * 2 * np.pi / 360
            altitude = shell['altitude'] * 1000
            mean_motion = np.sqrt(GM / (R + altitude)**3) * 60
            orbit_number, sat_number = shell['orbit'], shell['sat']
            num_of_sat = orbit_number * sat_number

            sat_lla_t = np.zeros((ts_total, orbit_number, sat_number, 3))
            for oid in range(orbit_number):
                raan = oid / orbit_number * 2 * np.pi
                for sid in range(sat_number):
                    mean_anomaly = (sid * 360 / sat_number + oid * 360 * F /
                                    num_of_sat) % 360 * 2 * np.pi / 360
                    satrec = Satrec()
                    satrec.sgp4init(
                        WGS84,  # gravity model
                        'i',  # 'a' = old AFSPC mode, 'i' = improved mode
                        oid * sat_number + sid,  # satnum: Satellite number
                        epoch,  # epoch: days since 1949 December 31 00:00 UT
                        2.8098e-05,  # bstar: drag coefficient (/earth radii)
                        6.969196665e-13,  # ndot: ballistic coefficient (revs/day)
                        0.0,  # nddot: second derivative of mean motion (revs/day^3)
                        0.001,  # ecco: eccentricity
                        0.0,  # argpo: argument of perigee (radians)
                        inclination,  # inclo: inclination (radians)
                        mean_anomaly,  # mo: mean anomaly (radians)
                        mean_motion,  # no_kozai: mean motion (radians/minute)
                        raan,  # nodeo: right ascension of ascending node (radians)
                    )
                    sat = EarthSatellite.from_satrec(satrec, ts)
                    cur = datetime.datetime(2022, 1, 1, 1, 0, 0)
                    t_ts = ts.utc(*cur.timetuple()[:5], ts_lst)  # [:4]:minute，[:5]:second
                    geocentric = sat.at(t_ts)
                    subpoint = wgs84.subpoint(geocentric)
                    # list: [subpoint.latitude.degrees] [subpoint.longitude.degrees] [subpoint.elevation.km]
                    for t in range(ts_total):
                        sat_lla_t[t, oid, sid] = (subpoint.latitude.degrees[t],
                                                subpoint.longitude.degrees[t],
                                                subpoint.elevation.km[t])
            pos_dir = os.path.join(dir, shell['name'], 'position')
            for t, sat_lla in enumerate(sat_lla_t):
                f = open(os.path.join(pos_dir, '%d.txt' % (t + 1)), 'w')
                for sat_lst in sat_lla:
                    for sat in sat_lst:
                        f.write('%f,%f,%f\n' % (sat[0], sat[1], sat[2]))
                    f.write('\n')
                f.close()
            sat_cbf_t_shell.append(to_cbf(sat_lla_t))

    isls_t_shell = isl_styles[isl_style](sat_cbf_t_shell)
    for i, isls_t in enumerate(isls_t_shell):
        isl_dir = os.path.join(dir, shell_lst[i]['name'], 'isl')

        isl_state = [ [list() for _ in range(shell_lst[i]['sat'])] 
                      for _ in range(shell_lst[i]['orbit'])]
        for t in range(ts_total):
            f1 = open(f"{isl_dir}/{t}-state.txt", 'w')
            f2 = open(f"{isl_dir}/{t}.txt", 'w')
            for oid, sat_lst in enumerate(isls_t[t]):
                for sid, isl_lst in enumerate(sat_lst):
                    # one line for each satellite
                    f1.write(f"{oid},{sid}:")
                    f1.write(' '.join(f"{isl[0]},{isl[1]},{isl[2]},{isl[3]:.2f}"
                        for isl in isl_lst))
                    f1.write('\n')

                    f2.write(f"{oid},{sid}|")
                    old_lst = isl_state[oid][sid]
                    old_del = [True] * len(old_lst)
                    new_add = [True] * len(isl_lst)
                    update = []
                    for i, old in enumerate(old_lst):
                        for j, new in enumerate(isl_lst):
                            if old[0] != new[0]:
                                continue
                            old_del[i] = False
                            new_add[j] = False
                            if abs(new[3] - old[3]) > 1e-2:
                                update.append(new)
                            else:
                                isl_lst[j] = old
                    # del some isls
                    f2.write(' '.join(
                        f"{isl[0]},{isl[1]},{isl[2]},{isl[3]:.2f}"
                        for isl, de in zip(old_lst, old_del) if de
                    ) + '|')
                    # update some isls
                    f2.write(' '.join(
                        f"{isl[0]},{isl[1]},{isl[2]},{isl[3]:.2f}"
                        for isl in update
                    ) + '|')
                    # add some isls
                    f2.write(' '.join(
                        f"{isl[0]},{isl[1]},{isl[2]},{isl[3]:.2f}"
                        for isl, add in zip(isl_lst, new_add) if add
                    ) + '\n')
                    isl_state[oid][sid] = isl_lst
                f1.write('\n')
                f2.write('\n')
            f1.close()
            f2.close()
    
    gs_cbf = to_cbf(GS_lat_long)
    bound_dis = _bound_gsl(antenna_elevation, shell['altitude'])
    gsls_t = gsl_styles[gsl_style](sat_cbf_t_shell, gs_cbf, antenna_number, bound_dis)
    gsl_state = [list() for _ in range(len(GS_lat_long))]
    for t, gsls in enumerate(gsls_t):
        f1 = open(f"{gsl_dir}/{t}-state.txt", 'w')
        f2 = open(f"{gsl_dir}/{t}.txt", 'w')
        for gid, gsl_lst in enumerate(gsls):
            # one line for each ground station
            f1.write(f"{gid}:")
            f1.write(' '.join(f"{gsl[0]},{gsl[1]},{gsl[2]},{gsl[3]},{gsl[4]:.2f}"
                for gsl in gsl_lst))
            f1.write('\n')

            f2.write(f"{gid}|")
            # add some isls
            old_lst = gsl_state[gid]
            old_del = [True] * len(old_lst)
            new_add = [True] * len(gsl_lst)
            update = []
            for i, old in enumerate(old_lst):
                for j, new in enumerate(gsl_lst):
                    if old[0] == new[0]:
                        old_del[i] = False
                        new_add[j] = False
                        if abs(new[4] - old[4]) > 1e-2:
                            update.append(new)
                        else:
                            gsl_lst[j] = old # if not update, remain old delay
            f2.write(' '.join(
                f"{gsl[0]},{gsl[1]},{gsl[2]},{gsl[3]},{gsl[4]:.2f}"
                for gsl, de in zip(old_lst, old_del) if de
            ) + '|')
            # update some gsls
            f2.write(' '.join(
                f"{gsl[0]},{gsl[1]},{gsl[2]},{gsl[3]},{gsl[4]:.2f}"
                for gsl in update
            ) + '|')
            # del some gsls
            f2.write(' '.join(
                f"{gsl[0]},{gsl[1]},{gsl[2]},{gsl[3]},{gsl[4]:.2f}"
                for gsl, add in zip(gsl_lst, new_add) if add
            ) + '\n')
            gsl_state[gid] = gsl_lst
        f1.close()
        f2.close()

def load_pos(path):
    f = open(path, 'r')
    lla_mat = []
    lla_lst = []
    oid, sid = 0, 0
    for line in f:
        if len(line) == 0 or line.isspace():
            lla_mat.append(lla_lst)
            lla_lst = []
            sid = 0
            oid += 1
            continue
        lla_lst.append(list(map(float, line.strip().split(','))))
    f.close()
    return lla_mat

def load_isl_state(path):
    f = open(path, 'r')
    isl_mat = []
    isl_lst = []
    oid, sid = 0, 0
    for line in f:
        if len(line) == 0 or line.isspace():
            isl_mat.append(isl_lst)
            isl_lst = []
            sid = 0
            oid += 1
            continue
        line = line[line.find(':')+1:].strip()
        isl_lst.append(line.split())
    f.close()
    return isl_mat

def load_gsl_state(path):
    f = open(path, 'r')
    gsl_lst = []
    gid = 0
    for line in f:
        line = line[line.find(':')+1:].strip()
        gsl_lst.append(line.split())
    f.close()
    return gsl_lst
