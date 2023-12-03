import os
import subprocess
import sys
import glob
import ctypes
# from line_profiler import LineProfiler


"""
Used in the remote machine for link updating, initializing links, damaging and recovering links and other functionalities。
author: Yangtao Deng (dengyt21@mails.tsinghua.edu.cn) and Zeqi Lai (zeqilai@tsinghua.edu.cn) 
"""

PID_FILENAME = 'container_pid.txt'
ASSIGN_FILENAME = 'assign.txt'
NOT_ASSIGNED = 'NA'
VXLAN_PORT = 4789
# FIXME
CLONE_NEWNET = 0x40000000
libc = ctypes.CDLL(None)

def _sat_name(shell_id, orbit_id, sat_id):
    return f'SH{shell_id+1}O{orbit_id+1}S{sat_id+1}'

def _gs_name(gid):
    return f'GS{gid+1}'

def _pid_matrix(path, pop = False):
    global _mat_cache
    if path not in _mat_cache:
        with open(path, 'r') as f:
            _mat_cache[path] = [
                [pid for pid in line.strip().split(' ')]
                for line in f if len(line) > 0 and not line.isspace()
            ]
    if pop:
        return _mat_cache.pop(path)
    return _mat_cache[path]

def _get_params(path):
    with open(path, 'r') as f:
        gs_mid = [int(mid) for mid in f.readline().split()]
        sat_mid_lst, ip_lst = [], []
        for line in f:
            if len(line) == 0 or line.isspace():
                break
            toks = line.strip().split(' ')
            orbit_num, shell_name = int(toks[0]), toks[1]
            sat_mid = [int(mid) for mid in f.readline().split(' ')]
            sat_mid_lst.append((orbit_num, shell_name, sat_mid))
        for line in f:
            ip_lst.append(line.strip())
    return gs_mid, sat_mid_lst, ip_lst

def _parse_isls(path):
    del_lst, update_lst, add_lst = [], [], []
    f = open(path, 'r')
    oid, sid = 0, 0
    for line in f:
        if len(line) == 0 or line.isspace():
            oid += 1
            sid = 0
            continue
        toks = line.strip().split('|')
        if len(toks[1]) > 0:
            for isl in toks[1].split(' '):
                i_o_s_d = isl.split(',')
                idx, isl_oid, isl_sid = int(i_o_s_d[0]),int(i_o_s_d[1]),int(i_o_s_d[2])
                del_lst.append((idx, oid, sid, isl_oid, isl_sid, i_o_s_d[3]))
        if len(toks[2]) > 0:
            for isl in toks[2].split(' '):
                i_o_s_d = isl.split(',')
                idx, isl_oid, isl_sid = int(i_o_s_d[0]),int(i_o_s_d[1]),int(i_o_s_d[2])
                update_lst.append((idx, oid, sid, isl_oid, isl_sid, i_o_s_d[3]))
        if len(toks[3]) > 0:
            for isl in toks[3].split(' '):
                i_o_s_d = isl.split(',')
                idx, isl_oid, isl_sid = int(i_o_s_d[0]),int(i_o_s_d[1]),int(i_o_s_d[2])
                add_lst.append((idx, oid, sid, isl_oid, isl_sid, i_o_s_d[3]))
        sid += 1
    f.close()
    return del_lst, update_lst, add_lst

def _parse_gsls(path):
    del_lst, update_lst, add_lst = [], [], []
    f = open(path, 'r')
    for gid, line in enumerate(f):
        if len(line) == 0 or line.isspace():
            continue
        toks = line.strip().split('|')
        if len(toks[1]) > 0:
            for isl in toks[1].split(' '):
                i_s_o_s_d = isl.split(',')
                idx, shell_id = int(i_s_o_s_d[0]), int(i_s_o_s_d[1])
                oid, sid = int(i_s_o_s_d[2]), int(i_s_o_s_d[3])
                del_lst.append((idx, gid, shell_id, oid, sid, i_s_o_s_d[4]))
        if len(toks[2]) > 0:
            for isl in toks[2].split(' '):
                i_s_o_s_d = isl.split(',')
                idx, shell_id = int(i_s_o_s_d[0]), int(i_s_o_s_d[1])
                oid, sid = int(i_s_o_s_d[2]), int(i_s_o_s_d[3])
                update_lst.append((idx, gid, shell_id, oid, sid, i_s_o_s_d[4]))
        if len(toks[3]) > 0:
            for isl in toks[3].split(' '):
                i_s_o_s_d = isl.split(',')
                idx, shell_id = int(i_s_o_s_d[0]), int(i_s_o_s_d[1])
                oid, sid = int(i_s_o_s_d[2]), int(i_s_o_s_d[3])
                add_lst.append((idx, gid, shell_id, oid, sid, i_s_o_s_d[4]))
    f.close()
    return del_lst, update_lst, add_lst

# name1 in local machine
def _del_link(idx, name1, name2):
    n1_n2 = f"{idx}-{name2}"
    fd = os.open('/run/netns/' + name1, os.O_RDONLY)
    libc.setns(fd, CLONE_NEWNET)
    os.close(fd)
    subprocess.check_call(('ip', 'link', 'del', n1_n2))

def _init_if(name, if_name, addr, delay, bw, loss):
    fd = os.open('/run/netns/' + name, os.O_RDONLY)
    libc.setns(fd, CLONE_NEWNET)
    os.close(fd)
    subprocess.check_call(('ip', 'addr', 'add', addr, 'dev', if_name))
    subprocess.check_call(
        ('tc', 'qdisc', 'add', 'dev', if_name, 'root',
         'netem', 'delay', delay+'ms', 'loss', loss+'%', 'rate', bw+'Gbit')
    )
    subprocess.check_call(('ip', 'link', 'set', if_name, 'up'))

def _update_if(name, if_name, delay, bw, loss):
    fd = os.open('/run/netns/' + name, os.O_RDONLY)
    libc.setns(fd, CLONE_NEWNET)
    os.close(fd)
    subprocess.check_call(
        ('tc', 'qdisc', 'change', 'dev', if_name, 'root',
        'netem', 'delay', delay + 'ms', 'rate', bw + 'Gbit', 'loss', loss + '%')
    )

def _update_link_intra_machine(idx, name1, name2, delay, bw, loss):
    n1_n2 = f"{idx}-{name2}"
    n2_n1 = f"{idx}-{name1}"
    _update_if(name1, n1_n2, delay, bw, loss)
    _update_if(name2, n2_n1, delay, bw, loss)

# name1 in local machine
def _update_link_local(idx, name1, name2, delay, bw, loss):
    n1_n2 = f"{idx}-{name2}"
    _update_if(name1, n1_n2, delay, bw, loss)

def _add_link_intra_machine(idx, name1, name2, prefix, delay, bw, loss):
    n1_n2 = f"{idx}-{name2}"
    n2_n1 = f"{idx}-{name1}"
    subprocess.check_call(
        ('ip', 'link', 'add', n1_n2, 'netns', name1,
         'type', 'veth', 'peer', n2_n1, 'netns', name2)
    )
    _init_if(name1, n1_n2, prefix+'.10/24', delay, bw, loss)
    _init_if(name2, n2_n1, prefix+'.40/24', delay, bw, loss)
    
def _add_link_inter_machine(idx, name1, name2, remote_ip, prefix, delay, bw, loss):
    n1_n2 = f"{idx}-{name2}"
    n2_n1 = f"{idx}-{name1}"
    subprocess.check_call(
        ('ip', 'link', 'add', n1_n2, 'type', 'vxlan',
         'id', str(idx), 'remote', remote_ip, 'dstport', VXLAN_PORT)
    )
    _init_if(name1, n1_n2, prefix+'.10/24', delay, bw, loss)
    _init_if(name2, n2_n1, prefix+'.40/24', delay, bw, loss)

def sn_init_nodes(dir, gs_mid, sat_mid_lst):
    def _load_netns(pid, name):
        netns_link = f'/run/netns/{name}'
        if not os.path.exists(netns_link):
            subprocess.check_call(('ln', '-s', f'/proc/{pid}/ns/net', netns_link))

    for shell_id, (orbit_num, shell_name, sat_mid) in enumerate(sat_mid_lst):
        if all(assign != machine_id for assign in sat_mid):
            continue
        shell_dir = f"{dir}/{shell_name}"
        overlay_dir = shell_dir + '/overlay'
        os.makedirs(overlay_dir, exist_ok=True)
        pid_file = open(shell_dir + '/' + PID_FILENAME, 'w', encoding='utf-8')
        for sid, assign in enumerate(sat_mid):
            if assign != machine_id:
                pid_file.write(' '.join(NOT_ASSIGNED for _ in range(orbit_num)) + '\n')
                continue
            print(f'[{machine_id}] Satellite: {shell_id},{sid},(0-{orbit_num})')
            for oid in range(orbit_num):
                name = _sat_name(shell_id, oid, sid)
                node_dir = f'{overlay_dir}/{name}'
                pid_file.write(str(pyctr.container_run(node_dir, name)) + ' ')
            pid_file.write('\n')
        pid_file.close()
    if len(gs_mid) > 0 and any(assign == machine_id for assign in gs_mid):
        gs_dir = f"{dir}/GS-{len(gs_mid)}"
        overlay_dir = gs_dir + '/overlay'
        os.makedirs(overlay_dir, exist_ok=True)
        pid_file = open(gs_dir + '/' + PID_FILENAME, 'w', encoding='utf-8')
        for gid, assign in enumerate(gs_mid):
            if assign != machine_id:
                pid_file.write(NOT_ASSIGNED + ' ')
                continue
            print(f'[{machine_id}] GS: {gid}/{len(gs_mid)}')
            name = _gs_name(gid)
            node_dir = f'{overlay_dir}/{name}'
            pid_file.write(str(pyctr.container_run(node_dir, name)) + ' ')
        pid_file.write('\n')
        pid_file.close()
    sn_operate_every_node(dir, sat_mid_lst, gs_mid, _load_netns)

def sn_update_network(
        dir, ts, sat_mid_lst, gs_mid, ip_lst,
        isl_bw, isl_loss, gsl_bw, gsl_loss
    ):
    for shell_id, (orbit_num, shell_name, sat_mid) in enumerate(sat_mid_lst):
        shell_dir = f"{dir}/{shell_name}"
        if not os.path.exists(shell_dir):
            continue
        del_cnt, update_cnt, add_cnt = 0, 0, 0
        del_lst, update_lst, add_lst = _parse_isls(f'{shell_dir}/{ts}.txt')
        for idx, oid, sid, isl_oid, isl_sid, delay in del_lst:
            if sat_mid[sid] == machine_id:
                del_cnt += 1
                _del_link(
                    idx,
                    _sat_name(shell_id, oid, sid),
                    _sat_name(shell_id, isl_oid, isl_sid)
                )
            elif sat_mid[isl_sid] == machine_id:
                del_cnt += 1
                _del_link(
                    idx,
                    _sat_name(shell_id, isl_oid, isl_sid),
                    _sat_name(shell_id, oid, sid)
                )
        for idx, oid, sid, isl_oid, isl_sid, delay in update_lst:
            if sat_mid[sid] == machine_id:
                update_cnt += 1
                if sat_mid[isl_sid] == machine_id:
                    _update_link_intra_machine(
                        idx,
                        _sat_name(shell_id, oid, sid),
                        _sat_name(shell_id, isl_oid, isl_sid),
                        delay, isl_bw, isl_loss
                    )
                else:
                    _update_link_local(
                        idx,
                        _sat_name(shell_id, oid, sid),
                        _sat_name(shell_id, isl_oid, isl_sid),
                        delay, isl_bw, isl_loss
                    )
            elif sat_mid[isl_sid] == machine_id:
                update_cnt += 1
                _update_link_local(
                    idx,
                    _sat_name(shell_id, isl_oid, isl_sid),
                    _sat_name(shell_id, oid, sid),
                    delay, isl_bw, isl_loss
                )
        for idx, oid, sid, isl_oid, isl_sid, delay in add_lst:
            if sat_mid[sid] == machine_id:
                add_cnt += 1
                if sat_mid[isl_sid] == machine_id:
                    _add_link_intra_machine(
                        idx,
                        _sat_name(shell_id, oid, sid),
                        _sat_name(shell_id, isl_oid, isl_sid),
                        f'10.{idx >> 8}.{idx & 0xFF}', delay, isl_bw, isl_loss
                    )
                else:
                    _add_link_inter_machine(
                        idx,
                        _sat_name(shell_id, oid, sid),
                        _sat_name(shell_id, isl_oid, isl_sid),
                        ip_lst[sat_mid[isl_sid]],
                        f'10.{idx >> 8}.{idx & 0xFF}', delay, isl_bw, isl_loss
                    )
            elif sat_mid[isl_sid] == machine_id:
                add_cnt += 1
                _add_link_inter_machine(
                    idx,
                    _sat_name(shell_id, isl_oid, isl_sid),
                    _sat_name(shell_id, oid, sid),
                    ip_lst[sat_mid[sid]],
                    f'10.{idx >> 8}.{idx & 0xFF}', delay, isl_bw, isl_loss
                )
        print(f"[{machine_id}] Shell {shell_id}:",
              f"{del_cnt} deleted, {update_cnt} updated, {add_cnt} added.")

    gs_dir = f"{dir}/GS-{len(gs_mid)}"
    # return
    if not os.path.exists(gs_dir):
        return
    del_cnt, update_cnt, add_cnt = 0, 0, 0
    del_lst, update_lst, add_lst = _parse_gsls(f'{gs_dir}/{ts}.txt')
    for idx, gid, shell_id, oid, sid, delay in del_lst:
        orbit_num, shell_name, sat_mid = sat_mid_lst[shell_id]
        if gs_mid[gid] == machine_id:
            del_cnt += 1
            _del_link(idx, _gs_name(gid), _sat_name(shell_id, oid, sid))
        elif sat_mid[sid] == machine_id:
            del_cnt += 1
            _del_link(idx, _sat_name(shell_id, isl_oid, isl_sid), _gs_name(gid))
    for idx, gid, shell_id, oid, sid, delay in update_lst:
        orbit_num, shell_name, sat_mid = sat_mid_lst[shell_id]
        if gs_mid[gid] == machine_id:
            update_cnt += 1
            if sat_mid[sid] == machine_id:
                _update_link_intra_machine(
                    idx,
                    _gs_name(gid), _sat_name(shell_id, oid, sid),
                    delay, gsl_bw, gsl_loss
                )
            else:
                _update_link_local(
                    idx,
                    _gs_name(gid), _sat_name(shell_id, oid, sid),
                    delay, gsl_bw, gsl_loss
                )
        elif sat_mid[sid] == machine_id:
            update_cnt += 1
            _update_link_local(
                idx,
                _sat_name(shell_id, oid, sid), _gs_name(gid),
                delay, gsl_bw, gsl_loss
            )
    for idx, gid, shell_id, oid, sid, delay in add_lst:
        orbit_num, shell_name, sat_mid = sat_mid_lst[shell_id]
        if gs_mid[gid] == machine_id:
            add_cnt += 1
            if sat_mid[sid] == machine_id:
                _add_link_intra_machine(
                    idx,
                    _gs_name(gid), _sat_name(shell_id, oid, sid),
                    f'9.{idx >> 8}.{idx & 0xFF}', delay, gsl_bw, gsl_loss
                )
            else:
                _add_link_inter_machine(
                    idx,
                    _gs_name(gid), _sat_name(shell_id, oid, sid), ip_lst[sat_mid[sid]],
                    f'9.{idx >> 8}.{idx & 0xFF}', delay, gsl_bw, gsl_loss
                )
        elif sat_mid[sid] == machine_id:
            add_cnt += 1
            _add_link_inter_machine(
                idx,
                _sat_name(shell_id, oid, sid), _gs_name(gid), ip_lst[gs_mid[gid]],
                f'9.{idx >> 8}.{idx & 0xFF}', delay, gsl_bw, gsl_loss
            )
    print(f"[{machine_id}] GSL:",
          f"{del_cnt} deleted, {update_cnt} updated, {add_cnt} added.")

def sn_container_check_call(pid, cmd):
    subprocess.check_call(
        ('nsenter', '-m', '-u', '-i', '-n', '-p', '-t', pid, *cmd)
    )

def sn_container_check_output(pid, cmd):
    return subprocess.check_output(
        ('nsenter', '-m', '-u', '-i', '-n', '-p', '-t', pid, *cmd)
    )

def sn_operate_every_node(dir, sat_mid_lst, gs_mid, func, *args):
    for shell_id, (orbit_num, shell_name, sat_mid) in enumerate(sat_mid_lst):
        pid_file = f"{dir}/{shell_name}/{PID_FILENAME}"
        if not os.path.exists(pid_file):
            continue
        pid_mat = _pid_matrix(pid_file)
        for sid, pid_lst in enumerate(pid_mat):
            for oid, pid in enumerate(pid_lst):
                if pid == NOT_ASSIGNED:
                    continue
                func(pid, _sat_name(shell_id, oid, sid), *args)
    gs_dir = f"{dir}/GS-{len(gs_mid)}"
    if not os.path.exists(gs_dir):
        return
    pid_mat = _pid_matrix(gs_dir + '/' + PID_FILENAME)
    assert len(pid_mat) == 1
    for gid, pid in enumerate(pid_mat[0]):
        if pid == NOT_ASSIGNED:
            continue
        func(int(pid), _gs_name(gid), *args)

def sn_init_route_daemons(dir, sat_mid_lst, gs_mid, conf_path):
    def _init_route_daemon(pid, name):
        bird_ctl_path = conf_path[:conf_path.rfind('/')] + '/bird.ctl'
        sn_container_check_call(pid, ('bird', '-c', conf_path, '-s', bird_ctl_path))
    sn_operate_every_node(dir, sat_mid_lst, gs_mid, _init_route_daemon)

def sn_ping(dir,sat_mid_lst, src_shell, src_oid, src_sid, dst_shell, dst_oid, dst_sid):
    # suppose src in this machine
    mat1 = _pid_matrix(f"{dir}/{sat_mid_lst[src_shell][1]}/{PID_FILENAME}")
    # TODO: dst in other machine
    mat2 = _pid_matrix(f"{dir}/{sat_mid_lst[dst_shell][1]}/{PID_FILENAME}")
    dst_addr = subprocess.check_output(
        "nsenter -m -u -i -n -p -t " + mat2[dst_sid][dst_oid] + " ip -br addr "
        "| awk '$1!=\"lo\"{print $3}'", shell=True
    ).decode().splitlines()[0]
    dst_addr = dst_addr[:dst_addr.rfind('/')]
    subprocess.run(
        ('nsenter', '-m', '-u', '-i', '-n', '-p', '-t', mat2[src_sid][src_oid],
         'ping', '-c', '4', '-i', '0.01', dst_addr),
         stdout=sys.stdout, stderr=subprocess.STDOUT
    )

def sn_clean(dir):
    for ns_link in glob.glob(f"/run/netns/SH*O*S*"):
        if os.path.islink(ns_link):
            os.remove(ns_link)
    for ns_link in glob.glob(f"/run/netns/G*"):
        if os.path.islink(ns_link):
            os.remove(ns_link)
    for pid_file in glob.glob(f"{dir}/[0-9]*/{PID_FILENAME}"):
        pid_mat = _pid_matrix(pid_file, True)
        for sid, pid_lst in enumerate(pid_mat):
            for oid, pid in enumerate(pid_lst):
                if pid == NOT_ASSIGNED:
                    continue
                try:
                    os.kill(int(pid), 9)
                except ProcessLookupError:
                    pass
        os.remove(pid_file)
    for pid_file in glob.glob(f"{dir}/GS-*/{PID_FILENAME}"):
        pid_mat = _pid_matrix(pid_file, True)
        for pid_lst in pid_mat:
            for gid, pid in enumerate(pid_lst):
                if pid == NOT_ASSIGNED:
                    continue
                try:
                    os.kill(int(pid), 9)
                except ProcessLookupError:
                    pass
        os.remove(pid_file)

def _change_sat_link_loss(pid, loss):
    out = sn_container_check_output(pid, ('ip', '-br', 'link', 'show')).decode()
    for line in out.splitlines():
        line = line.strip()
        if len(line) == 0 or line.startswith('lo'):
            continue
        dev_name = line.split('@')[0]
        sn_container_check_call(
            pid, 
            ('tc', 'qdisc', 'change', 'dev', dev_name, 'root', 'netem', 'loss', loss)
        )

def sn_damage(random_list, sat_mid_lst):
    for shell_id, oid, sid in random_list:
        pid_file = f"{dir}/{sat_mid_lst[shell_id][1]}/{PID_FILENAME}"
        if not os.path.exists(pid_file):
            continue
        pid_mat = _pid_matrix(pid_file)
        pid = pid_mat[sid][oid]
        _change_sat_link_loss(pid, '100%')
        print(f'[{machine_id}] damage sat: {shell_id},{oid},{sid}')

def sn_recover(damage_list, sat_mid_lst, sat_loss):
    for shell_id, oid, sid in damage_list:
        pid_file = f"{dir}/{sat_mid_lst[shell_id][1]}/{PID_FILENAME}"
        if not os.path.exists(pid_file):
            continue
        pid_mat = _pid_matrix(pid_file)
        pid = pid_mat[sid][oid]
        _change_sat_link_loss(pid, sat_loss)
        print(f'[{machine_id}] recover sat: {shell_id},{oid},{sid}')

if __name__ == '__main__':
    # C module
    import pyctr
    machine_id = int(sys.argv[1])
    _mat_cache = {}
    cmd = sys.argv[2]
    workdir = sys.argv[3]
    gs_mid, sat_mid_lst, ip_lst = _get_params(workdir + '/' + ASSIGN_FILENAME)
    if cmd == 'nodes':
        sn_clean(workdir)
        sn_init_nodes(workdir, gs_mid, sat_mid_lst)
    elif cmd == 'networks':
        # lp = LineProfiler()
        # sn_update_network = lp(sn_update_network)
        # lp.add_function(_update_link_intra_machine)
        sn_update_network(
            workdir, sys.argv[4], sat_mid_lst, gs_mid, ip_lst,
            sys.argv[5], sys.argv[6], sys.argv[7], sys.argv[8]
        )
        # with open('report.txt', 'w') as f:
            # lp.print_stats(f)
    elif cmd == 'routed':
        sn_init_route_daemons(workdir, sat_mid_lst, gs_mid, workdir + '/bird.conf')
    elif cmd == 'clean':
        sn_clean(workdir)
    elif cmd == 'ping':
        sn_ping(
            workdir, sat_mid_lst,
            int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6]),
            int(sys.argv[7]), int(sys.argv[8]), int(sys.argv[9]),
        )
    elif cmd == 'perf':
        pass
    else:
        print('Unknown command')
