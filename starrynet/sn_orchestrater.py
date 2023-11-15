import os
import subprocess
import sys
import gzip
from concurrent.futures import ThreadPoolExecutor

# C module
import pyctr

# from time import sleep
"""
Used in the remote machine for link updating, initializing links, damaging and recovering links and other functionalities。
author: Yangtao Deng (dengyt21@mails.tsinghua.edu.cn) and Zeqi Lai (zeqilai@tsinghua.edu.cn) 
"""

PID_FILENAME = 'container_pid.txt'
ASSIGN_FILENAME = 'assign.txt'
NOT_ASSIGNED = 'NA'

machine_id = None
workdir = None
init_pid_mat = None

def _sat_name(orbit_id, sat_id):
    return f'O{orbit_id+1}S{sat_id+1}'

def _get_delay(path):
    f = gzip.open(path, 'rt')
    ADJ = [ line.strip().split(',') for line in f ]
    f.close()
    return ADJ

def _get_params(path):
    with open(path, 'r') as f:
        orbit_num = int(f.readline())
        sat_assign_lst = [int(tok) for tok in f.readline().split(' ')]
        gs_assign_lst = [int(tok) for tok in f.readline().split(' ')]
    return orbit_num, sat_assign_lst, gs_assign_lst

def _get_init_pid(orbit_id, sat_id):
    global init_pid_mat
    if init_pid_mat is None:
        with open(workdir + '/' + PID_FILENAME, 'r') as f:
            init_pid_mat = [[pid for pid in line.strip().split(' ')] for line in f]
    return init_pid_mat[sat_id][orbit_id]

def sn_right_satellite(current_sat_id, current_orbit_id, orbit_num):
    if current_orbit_id == orbit_num - 1:
        return current_sat_id, 0
    else:
        return current_sat_id, current_orbit_id + 1

def sn_down_satellite(current_sat_id, current_orbit_id, sat_num):
    if current_sat_id == sat_num - 1:
        return 0, current_orbit_id
    else:
        return current_sat_id + 1, current_orbit_id

def sn_init_nodes(dir, orbit_num, sat_assign_lst, gs_assign_lst):
    sn_clear(dir)
    overlay_dir = dir + '/overlay'
    os.makedirs(overlay_dir, exist_ok=True)
    pid_file = open(dir + '/' + PID_FILENAME, 'w', encoding='utf-8')
    for sat_id, assign in enumerate(sat_assign_lst):
        if assign != machine_id:
            pid_file.write(' '.join(NOT_ASSIGNED for _ in range(orbit_num)) + '\n')
            continue
        print('sat:', sat_id)
        for orbit_id in range(orbit_num):
            sat_name = _sat_name(orbit_id, sat_id)
            sat_dir = f'{overlay_dir}/{sat_name}'
            pid_file.write(str(pyctr.container_run(sat_dir, sat_name)) + ' ')
        pid_file.write('\n')
    
    for gs_id, assign in enumerate(gs_assign_lst):
        if assign != machine_id:
            pid_file.write(NOT_ASSIGNED + '\n')
            continue
        gs_name = f'GS{gs_id+1}'
        gs_dir = f'{overlay_dir}/{gs_name}'
        pid_file.write(str(pyctr.container_run(gs_dir, gs_name)) + '\n')
    pid_file.close()

def sn_ISL_intra_machine(isl_idx, orbit, sat, peer_orbit, peer_sat, delay, bw, loss):
    cur_name, peer_name = _sat_name(orbit, sat), _sat_name(peer_orbit, peer_sat)
    for o, s, netns in ((orbit, sat, cur_name), (peer_orbit, peer_sat, peer_name)):
        pid = _get_init_pid(o, s)
        netns_link = f'/run/netns/{netns}'
        if os.path.exists(netns_link) or os.path.islink(netns_link):
            print('[Warning]netns exist:', netns_link)
            subprocess.check_call(('rm', netns_link))
        subprocess.check_call(('ln', '-s', f'/proc/{pid}/ns/net', netns_link))

    prefix = f'10.{isl_idx >> 8}.{isl_idx & 0xFF}'
    cur_peer = f'{cur_name}-{peer_name}'
    peer_cur = f'{peer_name}-{cur_name}'
    if subprocess.call(f"ip link show | grep '{cur_peer}'", shell=True) == 0:
        print('[Warning]veth exist:', cur_peer)
        subprocess.check_call(('ip', 'link', 'del', cur_peer))
    if subprocess.call(f"ip link show | grep '{peer_cur}'", shell=True) == 0:
        print('[Warning]veth exist:', peer_cur)
        subprocess.check_call(('ip', 'link', 'del', peer_cur))
    subprocess.check_call(
        ('ip', 'link', 'add', cur_peer, 'type', 'veth', 'peer', 'name', peer_cur))
    subprocess.check_call(('ip', 'link', 'set', cur_peer, 'netns', cur_name))
    subprocess.check_call(('ip', 'link', 'set', peer_cur, 'netns', peer_name))
    subprocess.check_call(
        ('ip', 'netns', 'exec', cur_name,
         'ip', 'addr', 'add', prefix+'.40/24', 'dev', cur_peer))
    subprocess.check_call(
        ('ip', 'netns', 'exec', cur_name,
         'tc', 'qdisc', 'add', 'dev', cur_peer, 'root',
        #  'netem', 'loss', loss+'%', 'rate', bw+'Gbps'))
         'netem', 'delay', delay+'ms', 'loss', loss+'%', 'rate', bw+'Gbps'))
    subprocess.check_call(
        ('ip', 'netns', 'exec', cur_name, 'ip', 'link', 'set', cur_peer, 'up'))

    subprocess.check_call(
        ('ip', 'netns', 'exec', peer_name,
         'ip', 'addr', 'add', prefix+'.10/24', 'dev', peer_cur))
    subprocess.check_call(
        ('ip', 'netns', 'exec', peer_name,
         'tc', 'qdisc', 'add', 'dev', peer_cur, 'root',
        #  'netem', 'loss', loss+'%', 'rate', bw+'Gbps'))
         'netem', 'delay', delay+'ms', 'loss', loss+'%', 'rate', bw+'Gbps'))
    subprocess.check_call(
        ('ip', 'netns', 'exec', peer_name, 'ip', 'link', 'set', peer_cur, 'up'))
    for netns in (cur_name, peer_name):
        os.remove(f'/run/netns/{netns}')
    
def sn_ISL_inter_machine(isl_idx, orbit, sat, peer_orbit, peer_sat, delay, bw, loss):
    raise NotImplementedError

def sn_GSL_intra_machine(gsl_idx, orbit, sat, gs, delay, bw, loss):
    raise NotImplementedError

def sn_init_networks(matrix, bw, loss, orbit_num, sat_assign_lst, gs_assign_lst):
    sat_num = len(sat_assign_lst)
    for sat_id, sat_assign in enumerate(sat_assign_lst):
        if sat_assign != machine_id:
            continue
        print('sat:', sat_id)
        for orbit_id in range(orbit_num):
            cur_idx = orbit_id * sat_num + sat_id
            right_sat, right_orbit = sn_right_satellite(sat_id, orbit_id, orbit_num)
            down_sat, down_orbit = sn_down_satellite(sat_id, orbit_id, sat_num)

            isl_indices = (cur_idx << 1, (cur_idx <<1) + 1)
            isl_orbits = (right_orbit, down_orbit)
            isl_sats = (right_sat, down_sat)
            for isl_idx, isl_orbit, isl_sat in zip(isl_indices, isl_orbits, isl_sats):
                if sat_assign_lst[isl_sat] == sat_assign:
                    sn_ISL_intra_machine(
                        isl_idx, orbit_id, sat_id, isl_orbit, isl_sat,
                        matrix[cur_idx][isl_orbit * sat_num + isl_sat], bw, loss
                    )
                else:
                    sn_ISL_inter_machine(
                        isl_idx, orbit_id, sat_id, isl_orbit, isl_sat,
                        matrix[cur_idx][isl_orbit * sat_num + isl_sat], bw, loss
                    )
    
    # for gs_id, gs_assign in enumerate(gs_assign_lst):
    #     if gs_assign != machine_id:
    #         continue
    #     print('gs:', gs_id)
    #     for sat_id, sat_assign in enumerate(sat_assign_lst):

def sn_establish_GSL(netns_list, matrix, GS_num, bw, loss):
    # starting links among satellites and ground stations
    constellation_size = orbit_num * sat_num
    for sat_id in range(constellation_size):
        for gs_id in range(constellation_size, constellation_size + GS_num):
            # matrix[i1][j1])==1 means a link between node i and node j
            delay = matrix[sat_id][gs_id]
            if float(delay) <= 0.01:
                continue
            # IP address  (there is a link between i and j)
            address_16_23 = (gs_id - constellation_size) & 0xff
            address_8_15 = sat_id & 0xff
            prefix = f'9.{address_16_23}.{address_8_15}'
            GSL_name = f'GSL_{sat_id + 1}-{gs_id + 1}'
            sat2gs = f'B{sat_id + 1}-eth{gs_id + 1}'
            gs2sat = f'B{gs_id + 1}-eth{sat_id + 1}'
            # Create internal network in docker.
            print(f"[Create {GSL_name}] {prefix}.0/24")
            subprocess.check_call(
                f"ip link add {sat2gs} type veth peer name {gs2sat} ", shell=True)
            subprocess.check_call(
                f"ip link set {sat2gs} netns {netns_list[sat_id]}", shell=True)
            subprocess.check_call(
                f"ip link set {gs2sat} netns {netns_list[gs_id]}", shell=True)
            subprocess.check_call(
                f"ip netns exec {netns_list[sat_id]} "
                f"ip addr add {prefix}.50/24 dev {sat2gs}", shell=True)
            subprocess.check_call(
                f"ip netns exec {netns_list[sat_id]} "
                f"tc qdisc add dev {sat2gs} root "
                f"netem delay {delay}ms loss {loss}% rate {bw}Gbps", shell=True)
            subprocess.check_call(
                f"ip netns exec {netns_list[sat_id]} "
                f"ip link set dev {sat2gs} up", shell=True)
            subprocess.check_call(
                f"ip netns exec {netns_list[gs_id]} "
                f"ip addr add {prefix}.60/24 dev {gs2sat}", shell=True)
            subprocess.check_call(
                f"ip netns exec {netns_list[gs_id]} "
                f"tc qdisc add dev {gs2sat} root "
                f"netem delay {delay}ms loss {loss}% rate {bw}Gbps", shell=True)
            subprocess.check_call(
                f"ip netns exec {netns_list[gs_id]} "
                f"ip link set dev {gs2sat} up", shell=True)
    for gs_id in range(constellation_size, constellation_size + GS_num):
        GS_name = f"GS_{gs_id + 1}"
        # Create default network and interface for GS.
        # TODO limit GS size to 256
        prefix = f'9.{gs_id - constellation_size}.{gs_id - constellation_size}'
        gs_int = f'B{gs_id + 1}-default'
        print(f"[Create {GS_name}] {prefix}.0/24")
        subprocess.check_call(
            f"ip netns exec {netns_list[gs_id]} "
            f"ip link add {gs_int} type dummy", shell=True)
        subprocess.check_call(
            f"ip netns exec {netns_list[gs_id]} "
            f"ip addr add {prefix}.10/24 dev {gs_int}", shell=True)
        subprocess.check_call(
            f"ip netns exec {netns_list[gs_id]} "
            f"ip link set dev {gs_int} up", shell=True)

def sn_container_exec(pid, cmd):
    return pyctr.container_exec(pid, tuple(arg.encode() for arg in cmd))

def sn_init_route_daemon(sat_assign_lst, bird_conf):
    for sat_id, sat_assign in enumerate(sat_assign_lst):
        if sat_assign != machine_id:
            continue
        print('sat:', sat_id)
        for orbit_id in range(orbit_num):
            sn_container_exec(
                int(_get_init_pid(orbit_id, sat_id)),
                ('bird', '-c', bird_conf)
            )

def sn_clear(dir):
    pid_path = dir + '/' + PID_FILENAME
    if os.path.exists(pid_path):
        pid_file = open(pid_path, 'r', encoding='utf-8')
        for line in pid_file:
            for pid in line.strip().split(' '):
                if pid == NOT_ASSIGNED:
                    continue
                os.kill(int(pid), 9)
        pid_file.close()
        os.remove(pid_path)
    overlay_dir = dir + '/overlay'
    if not os.path.exists(overlay_dir):
        return
    for entr in os.listdir(overlay_dir):
        merge_dir = f'{overlay_dir}/{entr}/rootfs'
        if os.system(f"mountpoint -q {merge_dir}") == 0:
            subprocess.check_call(('umount', merge_dir))

def sn_damage_link(orbit_id, sat_id):

    with os.popen(
            "docker exec -it " + str(container_id_list[sat_index]) +
            " ifconfig | sed 's/[ \t].*//;/^\(eth0\|\)\(lo\|\)$/d'") as f:
        ifconfig_output = f.readlines()
        for intreface in range(0, len(ifconfig_output), 2):
            subprocess.check_call("docker exec -d " + str(container_id_list[sat_index], shell=True) +
                      " tc qdisc change dev " +
                      ifconfig_output[intreface][:-1] +
                      " root netem loss 100%")
            print("docker exec -d " + str(container_id_list[sat_index]) +
                  " tc qdisc change dev " + ifconfig_output[intreface][:-1] +
                  " root netem loss 100%")

def sn_damage(random_list, container_id_list):
    pool = ThreadPoolExecutor()
    for random_satellite in random_list:
        pool.submit(sn_damage_link, int(random_satellite), container_id_list)
    pool.shutdown(wait=True)


def sn_recover_link(
    damaged_satellite,
    container_id_list,
    sat_loss,
):
    with os.popen(
            "docker exec -it " + str(container_id_list[damaged_satellite]) +
            " ifconfig | sed 's/[ \t].*//;/^\(eth0\|\)\(lo\|\)$/d'") as f:
        ifconfig_output = f.readlines()
        for i in range(0, len(ifconfig_output), 2):
            subprocess.check_call("docker exec -d " +
                      str(container_id_list[damaged_satellite], shell=True) +
                      " tc qdisc change dev " + ifconfig_output[i][:-1] +
                      " root netem loss " + str(sat_loss) + "%")
            print("docker exec -d " +
                  str(container_id_list[damaged_satellite]) +
                  " tc qdisc change dev " + ifconfig_output[i][:-1] +
                  " root netem loss " + str(sat_loss) + "%")


def sn_del_network(network_name):
    subprocess.check_call('docker network rm ' + network_name, shell=True)


def sn_stop_emulation():
    # subprocess.check_call("docker service rm constellation-test", shell=True)
    # with os.popen("docker rm -f $(docker ps -a -q)") as f:
    #     f.readlines()
    subprocess.check_call("for COMPOSE in $(docker compose ls | grep grid | awk '{print $3}', shell=True);"
        "do docker compose -f $COMPOSE down 2>/dev/null;"
        "done")
    subprocess.check_call(
        "for NETWORK in $(docker network ls | grep -o '\(La\|Le\|GS\, shell=True)\S*');"
        "do docker network rm $NETWORK;"
        "done"
    )


def sn_recover(damage_list, container_id_list, sat_loss):
    pool = ThreadPoolExecutor()
    for damaged_satellite in damage_list:
        pool.submit(sn_recover_link,
            int(damaged_satellite), container_id_list, sat_loss)
    pool.shutdown(wait=True)


# updating delays
def sn_update_delay(matrix, container_id_list, constellation_size):
    pool = ThreadPoolExecutor()
    for row in range(len(matrix)):
        for col in range(row, len(matrix[row])):
            if float(matrix[row][col]) <= 0:
                continue

            if row < col:
                pool.submit(sn_delay_change,
                    row, col, matrix[row][col],
                    container_id_list, constellation_size)
            else:
                pool.submit(sn_delay_change,
                    col, row, matrix[col][row],
                    container_id_list, constellation_size)
    pool.shutdown(wait=True)
    print("Delay updating done.\n")


def sn_delay_change(link_x, link_y, delay, container_id_list,
                    constellation_size):  # multi-thread updating delays
    if link_y <= constellation_size:
        subprocess.check_call("docker exec -d " + str(container_id_list[link_x], shell=True) +
                  " tc qdisc change dev B" + str(link_x + 1) + "-eth" +
                  str(link_y + 1) + " root netem delay " + str(delay) + "ms")
        subprocess.check_call("docker exec -d " + str(container_id_list[link_y], shell=True) +
                  " tc qdisc change dev B" + str(link_y + 1) + "-eth" +
                  str(link_x + 1) + " root netem delay " + str(delay) + "ms")
    else:
        subprocess.check_call("docker exec -d " + str(container_id_list[link_x], shell=True) +
                  " tc qdisc change dev B" + str(link_x + 1) + "-eth" +
                  str(link_y + 1) + " root netem delay " + str(delay) + "ms")
        subprocess.check_call("docker exec -d " + str(container_id_list[link_y], shell=True) +
                  " tc qdisc change dev B" + str(link_y + 1) + "-eth" +
                  str(link_x + 1) + " root netem delay " + str(delay) + "ms")


if __name__ == '__main__':
    machine_id = 0
    workdir = sys.argv[2]
    orbit_num, sat_assign_lst, gs_assign_lst = _get_params(
            workdir + '/' + ASSIGN_FILENAME)
    if sys.argv[1] == 'nodes':
        sn_init_nodes(workdir, orbit_num, sat_assign_lst, gs_assign_lst)
    elif sys.argv[1] == 'networks':
        sn_init_networks(
            _get_delay(workdir + '/1.txt.gz'), sys.argv[3], sys.argv[4],
            orbit_num, sat_assign_lst, gs_assign_lst
        )
    elif sys.argv[1] == 'routed':
        sn_init_route_daemon(sat_assign_lst, workdir + '/bird.conf')
    elif sys.argv[1] == 'clean':
        sn_clear(workdir)
    else:
        print('Unknown command')
