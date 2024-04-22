#!/usr/bin/python
# -*- coding: UTF-8 -*-
"""
StarryNet: empowering researchers to evaluate futuristic integrated space and terrestrial networks.
author: Zeqi Lai (zeqilai@tsinghua.edu.cn) and Yangtao Deng (dengyt21@mails.tsinghua.edu.cn)
"""
import time
import threading
import zipfile
import math
from starrynet.sn_observer import *
from starrynet.sn_utils import *

ASSIGN_FILENAME = 'assign.txt'

BIRD_CONF_TEXT = """\
log "/var/log/bird.log" { warning, error, auth, fatal, bug };
protocol device {
}
protocol direct {
    disabled;       # Disable by default
    ipv4;           # Connect to default IPv4 table
    ipv6;           # ... and to default IPv6 table
}
protocol kernel {
    ipv4 {          # Connect protocol to IPv4 table by channel
        export all; # Export to protocol. default is export none
    };
}
# protocol static {
#     ipv4;           # Again, IPv6 channel with default options
# }
protocol ospf{
    ipv4 {
        import all;
    };
    area 0 {
    interface "SH*O*S*" {
        type broadcast; # Detected by default
        cost 256;
        hello %d;
    };
    interface "GS*" {
        type broadcast; # Detected by default
        cost 256;
        hello %d;
    };
    interface "POP" {
        type broadcast; # Detected by default
        cost 256;
        hello %d;
    };
    };
}
"""

def _sat_name(shell_id, orbit_id, sat_id):
    return f'SH{shell_id+1}O{orbit_id+1}S{sat_id+1}'

def _sat2idx(sat_name):
    idx1 = sat_name.find('O')
    idx2 = sat_name.find('S', idx1)
    shell_id = int(sat_name[2:idx1])-1
    oid, sid = int(sat_name[idx1+1:idx2])-1, int(sat_name[idx2+1:])-1
    return shell_id, oid, sid

def _gs2idx(gs_name):
    return int(node[2:])-1

def _gs_name(gid):
    return f'GS{gid+1}'

class RemoteMachine:
    
    def __init__(self, id, host, port, username, password, 
                 shell_lst, experiment_name, local_dir, gs_dirname):
        self.id = id
        self.shell_lst = shell_lst
        self.local_dir = local_dir
        self.gs_dirname = gs_dirname
        self.ssh, self.sftp = sn_connect_remote(
            host = host,
            port = port,
            username = username,
            password = password,
        )
        sn_remote_cmd(self.ssh, 'mkdir ~/' + experiment_name)
        self.dir = sn_remote_cmd(self.ssh, 'echo ~/' + experiment_name)
        self.sftp.put(
            os.path.join(os.path.dirname(__file__), 'sn_orchestrater.py'),
            self.dir + '/sn_orchestrater.py'
        )
        self.sftp.put(
            os.path.join(os.path.dirname(__file__), 'pyctr.c'),
            self.dir + '/pyctr.c'
        )
        self.sftp.put(
            os.path.join(self.local_dir, 'bird.conf'),
            self.dir + '/bird.conf'
        )
        self.sftp.put(
            os.path.join(self.local_dir, ASSIGN_FILENAME),
            self.dir + '/' + ASSIGN_FILENAME
        )

    def init_nodes(self):
        sn_remote_wait_output(
            self.ssh,
            f"python3 {self.dir}/sn_orchestrater.py nodes {self.id} {self.dir}"
        )
    
    def get_nodes(self):
        lines = sn_remote_cmd(
            self.ssh,
            f"python3 {self.dir}/sn_orchestrater.py list {self.id} {self.dir}"
        ).splitlines()[1:]
        nodes = [
            line.split()[0] for line in lines
        ]
        return nodes
    
    def init_network(self, isl_bw, isl_loss, gsl_bw, gsl_loss):
        for shell in self.shell_lst:
            rmt_path = f"{self.dir}/{shell['name']}.zip"
            rmt_f = self.sftp.open(rmt_path, "wb")
            zip_f = zipfile.ZipFile(rmt_f, mode='w')
            pattern = os.path.join(self.local_dir, shell['name'], 'isl', '*.txt')
            for isl_txt in glob.glob(pattern):
                zip_f.write(isl_txt, f"{shell['name']}/{os.path.basename(isl_txt)}")
            zip_f.close()
            rmt_f.close()
            sn_remote_cmd(self.ssh, f"python3 -m zipfile -e {rmt_path} {self.dir}")
        if self.gs_dirname:
            rmt_path = f"{self.dir}/{self.gs_dirname}.zip"
            rmt_f = self.sftp.open(rmt_path, "wb")
            zip_f = zipfile.ZipFile(rmt_f, mode='w')
            pattern = os.path.join(self.local_dir, self.gs_dirname, 'gsl', '*.txt')
            for gsl_txt in glob.glob(pattern):
                zip_f.write(
                    gsl_txt,
                    f"{self.gs_dirname}/{os.path.basename(gsl_txt)}"
                )
            zip_f.close()
            rmt_f.close()
            sn_remote_cmd(self.ssh, f"python3 -m zipfile -e {rmt_path} {self.dir}")
        self.update_network(0, isl_bw, isl_loss, gsl_bw, gsl_loss)

    def update_network(self, t, isl_bw, isl_loss, gsl_bw, gsl_loss):
        sn_remote_wait_output(
            self.ssh,
            f"python3 {self.dir}/sn_orchestrater.py networks {self.id} {self.dir} "
            f"{t} {isl_bw} {isl_loss} {gsl_bw} {gsl_loss}"
        )
    
    def init_routed(self, nodes):
        print(sn_remote_cmd(
            self.ssh,
            f"python3 {self.dir}/sn_orchestrater.py routed {self.id} {self.dir} "
            +','.join(nodes)
        ))
    
    def get_IP(self, node):
        lines = sn_remote_cmd(
            self.ssh,
            f"python3 {self.dir}/sn_orchestrater.py IP {self.id} {self.dir} {node}"
        ).splitlines()
        IP_dict = {}
        for line in lines:
            dev_IP = line.strip().split()
            IP_dict[dev_IP[0]] = dev_IP[1]
        return IP_dict

    def ping_async(self, res_path, src, dst):
        def _ping_inner(ssh, dir, res_path, src, dst):
            output = sn_remote_cmd(
                ssh,
                f"python3 {dir}/sn_orchestrater.py ping {self.id} {dir} "
                f"{src} {dst} 2>&1"
            )
            with open(res_path, 'w') as f:
                f.write(output)
        thread = threading.Thread(
            target=_ping_inner,
            args=(self.ssh, self.dir, res_path, src, dst)
        )
        thread.start()
        return thread
    
    def iperf_async(self, res_path, src, dst):
        def _iperf_inner(ssh, dir, res_path, src, dst):
            output = sn_remote_cmd(
                ssh,
                f"python3 {self.dir}/sn_orchestrater.py iperf {self.id} {self.dir} "
                f"{src} {dst} 2>&1"
            )
            with open(res_path, 'w') as f:
                f.write(output)

        thread = threading.Thread(
            target=_iperf_inner,
            args=(self.ssh, self.dir, res_path, src, dst)
        )
        thread.start()
        return thread
    
    def sr(self, src, dst, next_hop):
        sn_remote_cmd(
            self.ssh,
            f"python3 {self.dir}/sn_orchestrater.py sr {self.id} {self.dir} "
            f"{src} {dst} {next_hop} 2>&1"
        )

    def check_route(self, res_path, sat):
        output = sn_remote_cmd(
            self.ssh,
            f"python3 {self.dir}/sn_orchestrater.py rtable {self.id} {self.dir} "
            f"{sat} 2>&1"
        )
        with open(res_path, 'w') as f:
            f.write(output)
    
    def check_utility(self, res_path):
        output = sn_remote_cmd(self.ssh, "vmstat 2>&1")
        with open(res_path, 'w') as f:
            f.write(output)
        
    def damage(self, random_lst):
        print(sn_remote_cmd(
            self.ssh,
            f"python3 {self.dir}/sn_orchestrater.py damage {self.id} {self.dir} "
            + ','.join(random_lst)
        ))
        
    def recovery(self, sat_loss):
        sn_remote_cmd(
            self.ssh,
            f"python3 {self.dir}/sn_orchestrater.py recovery {self.id} {self.dir} "
            f"{sat_loss}"
        )

    def clean(self):
        sn_remote_cmd(
            self.ssh,
            f"python3 {self.dir}/sn_orchestrater.py clean {self.id} {self.dir}"
        )

class StarryNet():

    def __init__(self, configuration_file_path, GS_lat_long, hello_interval):
        # Initialize constellation information.
        sn_args = sn_load_file(configuration_file_path)
        self.shell_lst = sn_args.shell_lst
        self.gs_lat_long = GS_lat_long
        self.link_style = sn_args.link_style
        self.link_policy = sn_args.link_policy
        self.IP_version = sn_args.IP_version
        self.step = sn_args.step
        self.duration = sn_args.duration
        self.sat_bandwidth = sn_args.sat_bandwidth
        self.sat_ground_bandwidth = sn_args.sat_ground_bandwidth
        self.sat_loss = sn_args.sat_loss
        self.sat_ground_loss = sn_args.sat_ground_loss
        self.antenna_number = sn_args.antenna_number
        self.elevation = sn_args.antenna_elevation
        self.configuration_dir = os.path.dirname(
            os.path.abspath(configuration_file_path))
        self.experiment_name = sn_args.cons_name\
            +'-'+ sn_args.link_style +'-'+ sn_args.link_policy
        self.gs_dirname = 'GS-' + str(len(self.gs_lat_long))
        for shell_id, shell in enumerate(self.shell_lst):
            shell['name'] = f"{shell_id}_{shell['altitude']}-{shell['inclination']}"\
                            f"-{shell['orbit']}-{shell['sat']}"\
                            f"-{shell['phase_shift']}"

        self.local_dir = os.path.join(self.configuration_dir, self.experiment_name)
        self._init_local(hello_interval)
        # Initiate a necessary delay and position data for emulation
        calculate_delay(
            self.local_dir, self.duration, self.step, self.shell_lst, self.link_style,
            self.gs_lat_long, self.antenna_number, self.elevation, self.link_policy
        )
        (self.remote_lst,
         self.sat_mid_lst, self.gs_mid) = self._assign_remote(sn_args.machine_lst)

        self.events = []
    
    def _init_local(self, hello_interval):
        for txt_file in glob.glob(os.path.join(self.local_dir, '*.txt')):
            os.remove(txt_file)
        for shell in self.shell_lst:
            os.makedirs(os.path.join(self.local_dir, shell['name']), exist_ok=True)
        os.makedirs(os.path.join(self.local_dir, self.gs_dirname), exist_ok=True)
        with open(os.path.join(self.local_dir, 'bird.conf'), 'w') as f:
            f.write(BIRD_CONF_TEXT % (hello_interval, hello_interval, hello_interval))

    def _assign_remote(self, machine_lst):
        # TODO: better partition
        remote_lst = []
        if len(self.shell_lst) * 2 <= len(machine_lst):
            # need intra-shell partition
            machine_per_shell = len(machine_lst) // len(self.shell_lst)
            raise NotImplementedError
        else:
            # only divide shell
            shell_per_machine = len(self.shell_lst) // len(machine_lst)
            remainder = len(self.shell_lst) % len(machine_lst)

            shell_id = 0
            sat_mid_lst = []
            assigned_shell_lst = []
            for i, remote in enumerate(machine_lst):
                shell_num = shell_per_machine
                if i < remainder:
                    shell_num += 1
                assigned_shells = [
                    self.shell_lst[j] for j in range(shell_id, shell_id + shell_num)
                ]
                # all satellites of a shell assigned to a single machine
                sat_mid_lst.extend([
                    (i,) * shell['sat'] for shell in assigned_shells
                ])
                assigned_shell_lst.append(assigned_shells)
                shell_id += shell_num
            gs_mid = []
            # TODO: better ground station assign
            with open(os.path.join(self.local_dir, self.gs_dirname,'gsl','0.txt'))as f:
                for line in f:
                    line = line.strip()
                    if len(line) == 0:
                        continue
                    init = line.split('|')[3]
                    if len(init) == 0:
                        gs_mid.append(0)
                        continue
                    gsl = init.split(' ')[0].split(',')
                    shell_id, sid = int(gsl[1]), int(gsl[3])
                    mid = sat_mid_lst[shell_id][sid]
                    gs_mid.append(mid)
            with open(os.path.join(self.local_dir, ASSIGN_FILENAME), 'w') as f:
                f.write(' '.join(str(mid) for mid in gs_mid) + '\n')
                # every shell
                for sat_mid, shell in zip(sat_mid_lst, self.shell_lst):
                    f.write(
                        str(shell['orbit']) + ' ' + shell['name'] + '\n'
                        + ' '.join(str(mid) for mid in sat_mid) + '\n'
                    )
                f.write('\n')
                for remote in machine_lst:
                    f.write(remote['IP'] + '\n')

        for i, remote in enumerate(machine_lst):
            remote_lst.append(RemoteMachine(
                i,
                remote['IP'],
                remote['port'],
                remote['username'],
                remote['password'],
                assigned_shell_lst[i],
                self.experiment_name,
                self.local_dir,
                self.gs_dirname if i in gs_mid else None
                )
            )
        return remote_lst, sat_mid_lst, gs_mid

    def create_nodes(self):
        print('Initializing nodes ...')
        begin = time.time()
        for remote in self.remote_lst:
            remote.init_nodes()
        print("Node initialization:", time.time() - begin, "s consumed.")
        self._load_node_map()

    def _load_node_map(self):
        self.node_map = {}
        self.undamaged_lst = list()
        self.total_sat_lst = list()
        for remote in self.remote_lst:
            for node in remote.get_nodes():
                if node.startswith('Error'):
                    print(node)
                    exit(1)
                if node.startswith('SH'):
                    self.undamaged_lst.append(node)
                    self.total_sat_lst.append(node)
                self.node_map[node.strip()] = remote

    def create_links(self):
        print('Initializing links ...')
        thread_lst = []
        begin = time.time()
        for remote in self.remote_lst:
            thread = threading.Thread(
                target=remote.init_network,
                args=(self.sat_bandwidth,
                      self.sat_loss,
                      self.sat_ground_bandwidth,
                      self.sat_ground_loss),
            )
            thread.start()
            thread_lst.append(thread)
        for thread in thread_lst:
            thread.join()
        print("Link initialization:", time.time() - begin, 's consumed.')

    def run_routing_daemon(self, node_lst='all'):
        print('Initializing routing ...')
        if node_lst == 'all':
            for remote in self.remote_lst:
                remote.init_routed(['all'])
            print("Routing daemon initialized. Wait 30s for route converged")
        else:
            rtd_lsts = {machine:[] for machine in self.remote_lst}
            for node in node_lst:
                rtd_lsts[self.node_map[node]].append(node)
            for remote, nodes in rtd_lsts.items():
                if len(nodes) > 0:
                    remote.init_routed(nodes)
        
        for i in range(30):
            print(f'\r{i} / 30', end=' ')
            time.sleep(1)
        print("Routing started!")

    # static information
    def get_distance(self, node1, node2, time_index):
        def _get_xyz(node):
            if node.startswith('SH'):
                shell_id, oid, sid = _sat2idx(node)
                shell = self.shell_lst[shell_id]
                lla_mat = load_pos(os.path.join(
                    self.local_dir,
                    shell['name'],
                    'position',
                    f'{time_index}.txt'
                ))
                return to_cbf(lla_mat[oid][sid])
            elif node.startswith('GS'):
                return to_cbf(self.gs_lat_long[_gs2idx(node)])
            else:
                raise NotImplementedError

        xyz1, xyz2 = _get_xyz(node1), _get_xyz(node2)
        dx, dy, dz = xyz1[0] - xyz2[0], xyz1[1] - xyz2[1], xyz1[2] - xyz2[2]
        return math.sqrt(dx * dx + dy * dy + dz * dz)

    def get_neighbors(self, sat, time_index):
        if not sat.startswith('SH'):
            raise RuntimeError('Not a satellite')
        shell_id, oid, sid = _sat2idx(sat)
        shell = self.shell_lst[shell_id]

        isl_mat = load_isl_state(os.path.join(
            self.local_dir,
            shell['name'],
            'isl',
            f'{time_index}-state.txt'
        ))
        neighbors = []
        for isl in isl_mat[oid][sid]:
            isl = isl.split(',')
            neighbors.append(_sat_name(shell_id, int(isl[1]), int(isl[2])))
        for orbit, isls_lst in enumerate(isl_mat):
            for sat, isls in enumerate(isls_lst):
                for isl in isls:
                    isl = isl.split(',')
                    if int(isl[1]) == oid and int(isl[2]) == sid:
                        neighbors.append(_sat_name(shell_id, orbit, sat))
        return neighbors

    def get_GSes(self, sat, time_index):
        if not sat.startswith('SH'):
            raise RuntimeError('Not a Satellite')
        shell_id, oid, sid = _sat2idx(sat)
        shell = self.shell_lst[shell_id]

        gsl_lst = load_gsl_state(os.path.join(
            self.local_dir,
            self.gs_dirname,
            'gsl',
            f'{time_index}-state.txt'
        ))
        GSes = []
        for gid, gsls in enumerate(gsl_lst):
            for gsl in gsls:
                gsl = gsl.split(',')
                if int(gsl[1]) == shell_id \
                and int(gsl[2]) == oid \
                and int(gsl[3]) == sid:
                    GSes.append(_gs_name(gid))
        return GSes

    def get_position(self, node, time_index):
        if node.startswith('SH'):
            shell_id, oid, sid = _sat2idx(node)
            shell = self.shell_lst[shell_id]

            lla_mat = load_pos(os.path.join(
                self.local_dir,
                shell['name'],
                'position',
                f'{time_index}.txt'
            ))
            return lla_mat[oid][sid]
        elif node.startswith('GS'):
            return self.gs_lat_long[_gs2idx(node)]
        else:
            raise NotImplementedError

    def get_IP(self, node):
        if not hasattr(self, 'node_map'):
            self._load_node_map()
        return self.node_map[node].get_IP(node)

    # dynamic events
    def get_utility(self, t):
        def _check_utility(real_t):
            for mid, machine in enumerate(self.remote_lst):
                machine.check_utility(os.path.join(
                    self.local_dir, f'{real_t}-utility-machine{mid}.txt')
                )
        self.events.append((t, _check_utility,))

    def set_damage(self, damaging_ratio, t):
        def _damage(real_t, damaging_ratio):
            damage_lsts = {machine:[] for machine in self.remote_lst}
            cur_num = len(self.undamaged_lst)
            need_damage_num = min(len(self.total_sat_lst) * damaging_ratio, cur_num)
            while(cur_num - len(self.undamaged_lst) < need_damage_num):
                sat = self.undamaged_lst.pop(
                    random.randint(0, len(self.undamaged_lst) - 1)
                )
                machine = self.node_map[sat]
                damage_lsts[machine].append(sat)
            for machine, lst in damage_lsts.items():
                machine.damage(lst)
        self.events.append((t, _damage, damaging_ratio,))

    def set_recovery(self, t):
        def _recovery(real_t):
            for machine in self.remote_lst:
                machine.recovery(self.sat_loss)
            self.undamaged_lst = self.total_sat_lst.copy()
        self.events.append((t, _recovery,))

    def check_routing_table(self, node, t):
        def _check_route(real_t, node):
            machine = self.node_map[node]
            machine.check_route(
                os.path.join(self.local_dir, f'{real_t}-route-{node}.txt'),
                node
            )
        self.events.append((t, _check_route, node,))

    def set_next_hop(self, src, dst, next_hop, t):
        def _set_next_hop(real_t, src, dst, next_hop):
            machine = self.node_map[src]
            machine.sr(src, dst, next_hop)
        self.events.append((t, _set_next_hop, src, dst, next_hop))

    def set_ping(self, src, dst, t):
        def _ping(real_t, src, dst):
            machine = self.node_map[src]
            self.ping_threads.append(machine.ping_async(
                os.path.join(self.local_dir, f'{real_t}-ping-{src}-{dst}.txt'),
                src, dst
            ))
        self.events.append((t, _ping, src, dst))

    def set_iperf(self, src, dst, t):
        def _iperf(real_t, src, dst):
            machine = self.node_map[src]
            self.iperf_threads.append(machine.iperf_async(
                os.path.join(self.local_dir, f'{real_t}-iperf-{src}-{dst}.txt'),
                src, dst
            ))
        self.events.append((t, _iperf, src, dst))
    
    def _event(self, real_t):
        while len(self.events) > 0 and self.events[-1][0] <= real_t:
            event = self.events.pop(-1)
            event[1](real_t, *event[2:])

    def start_emulation(self):
        self.events.sort(key=lambda x:x[0], reverse=True)

        if not hasattr(self, 'node_map'):
            self._load_node_map()

        self.ping_threads = []
        self.iperf_threads = []
        t = 0.0
        tid = 1
        while t < self.duration:
            start = time.time()
            print("\nTrigger events at", t, "s ...")
            self._event(t)
            print("Update networks ...")
            update_start = time.time()
            if tid < self.duration:
                conn_threads = []
                for remote in self.remote_lst:
                    thread = threading.Thread(
                        target=remote.update_network,
                        args=(tid,
                            self.sat_bandwidth,
                            self.sat_loss,
                            self.sat_ground_bandwidth,
                            self.sat_ground_loss
                    ))
                    thread.start()
                    conn_threads.append(thread)
                for thread in conn_threads:
                    thread.join()
            end = time.time()
            print(end-start, "s elapsed,", end-update_start, "s for network update")
            if end - start < 1:
                print('Sleep', 1 + start - end, 's')
                time.sleep(1 + start - end)
            t += self.step
            tid += 1
        for ping_thread in self.ping_threads:
            ping_thread.join()
        for iperf_thread in self.iperf_threads:
            iperf_thread.join()

    def clean(self):
        print("Removing containers and links...")
        for remote in self.remote_lst:
            remote.clean()
        print("All containers and links remoted.")
