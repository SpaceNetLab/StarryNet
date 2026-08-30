#!/usr/bin/python3
import os
import subprocess
import ctypes
import ipaddress
from typing import Dict, List
from enum import Enum
# from line_profiler import LineProfiler

try:
    import pyctr
    import pynetlink
except ModuleNotFoundError as exc:
    raise RuntimeError(
        "StarryNet C extensions are not installed. "
        "Reinstall the package or rebuild the extensions before running."
    ) from exc

# FIXME
NETNS_DIR = '/run/netns'

_libc = ctypes.CDLL(None)

def _switch_netns(node_pid: int):
    CLONE_NEWNET = 0x40000000
    pid_fd = os.open(f'/proc/{node_pid}/ns/net', os.O_RDONLY)
    _libc.setns(pid_fd, CLONE_NEWNET)
    os.close(pid_fd)

def _sysctl(param: str, value: str, check: bool = True):
    try:
        fd = os.open(f'/proc/sys/{param.replace(".", "/")}', os.O_WRONLY)
        os.write(fd, value.encode())
        os.close(fd)
    except (FileNotFoundError, PermissionError):
        if check:
            raise

class NetInterface:
    def __init__(self, if_idx: int, ipv4: ipaddress.IPv4Interface = None, ipv6: ipaddress.IPv6Interface = None):
        self.if_idx = if_idx
        self.ipv4 = ipv4
        self.ipv6 = ipv6

class NodeStatus(Enum):
    UP = 1
    DOWN = 2

class Node:
    """Node object representing a network node in the orchestrator"""
    
    def __init__(self, name: str, node_dir: str, node_id: int = 0):
        self.name = name
        self.node_id = node_id
        self.pid = pyctr.container_run(node_dir, name)
        self.status = NodeStatus.UP
        netns_link = f'{NETNS_DIR}/{name}'
        if os.path.islink(netns_link):
            os.unlink(netns_link)
        subprocess.check_call(('ln', '-s', f'/proc/{self.pid}/ns/net', netns_link))
        _switch_netns(self.pid)
        _sysctl('net.ipv4.conf.all.forwarding', '1')
        _sysctl('net.ipv6.conf.all.forwarding', '1', check=False)

        self.socket_fd = pynetlink.init_socket(self.pid)

        self.idle_links: List[NetInterface] = list()
        self.peer2link: Dict[str, NetInterface] = dict()
        
        # Initialize loopback addresses
        self._init_loopback()
    
    def __lt__(self, other):
        return self.pid < other.pid

    def _init_loopback(self):

        _switch_netns(self.pid)
        pynetlink.if_up('lo', self.socket_fd)
        _sysctl('net.mpls.conf.lo.input', '1', check=False)

        addr4 = ipaddress.IPv4Interface(
            f"16.{(self.node_id >> 8) & 0xFF}.{self.node_id & 0xFF}.1/32")
        addr6 = ipaddress.IPv6Interface(
            f"2000::{self.node_id:04x}/128"
        )
        lo_link = NetInterface(1, addr4, addr6)

        pynetlink.modify_addr(True, 'lo', addr4.packed, addr4.network.prefixlen, self.socket_fd)
        pynetlink.modify_addr(True, 'lo', addr6.packed, addr6.network.prefixlen, self.socket_fd)
        pynetlink.if_up('lo', self.socket_fd)

        self.peer2link['lo'] = lo_link

    def __del__(self):
        """Destructor to cleanup resources"""
        try:
            os.kill(self.pid, 9)
            netns_link = f'{NETNS_DIR}/{self.name}'
            if os.path.islink(netns_link):
                os.remove(netns_link)
            if self.socket_fd >= 0:
                pynetlink.close_socket(self.socket_fd)
        except:
            pass  # Ignore errors during cleanup
    
    def run_command(self, command, *args, **kwargs):
        """Run a command inside the node's network namespace"""
        return subprocess.Popen(
            ('nsenter', '-m', '-u', '-i', '-n', '-p', '-t', str(self.pid), *command),
            *args, **kwargs
        )

    def register_if(self, if_name: str, if_idx: int):
        self.peer2link[if_name] = NetInterface(if_idx = if_idx)

    def init_if(self, if_name: str, addr: str, addr6: str, delay: str, bw: str, loss: str):
        addr = ipaddress.IPv4Interface(addr)
        addr6 = ipaddress.IPv6Interface(addr6)
        _switch_netns(self.pid)
        pynetlink.modify_addr(True, if_name, addr.packed, addr.network.prefixlen, self.socket_fd)
        pynetlink.modify_addr(True, if_name, addr6.packed, addr6.network.prefixlen, self.socket_fd)
        pynetlink.traffic_control(if_name, delay, bw, loss, self.socket_fd)
        pynetlink.if_up(if_name, self.socket_fd)
        link = self.peer2link.get(if_name)
        if link is not None:
            link.ipv4 = addr
            link.ipv6 = addr6

        _sysctl(f'net.mpls.conf.{if_name}.input', '1', check=False)

    def update_if(self, if_name: str, delay: str, bw: str, loss: str):
        _switch_netns(self.pid)
        pynetlink.traffic_control(if_name, delay, bw, loss, self.socket_fd)

    def modify_routes(self, routes: List):
        _switch_netns(self.pid)
        pynetlink.modify_routes(routes, self.socket_fd)

    def del_if(self, ifname: str):
        _switch_netns(self.pid)
        pynetlink.del_link(ifname, self.socket_fd)

class OrchestratorContext:
    """Context object to maintain state for orchestrator"""
    
    def __init__(self, workdir):
        self.workdir = workdir

        self._main_net_sock_fd = pynetlink.init_socket()

        self.nodes: Dict[str, Node] = {}
        self.damage_lst: List[Node] = []

    def __del__(self):
        try:
            os.close(self._main_net_sock_fd)
        except:
            pass

    def clean(self):
        for node in self.nodes.values():
            del node
        
        self.nodes.clear()
        self.damage_lst.clear()

    def init_nodes(self, base_dir, node_configs):
        """
        Initialize nodes with unique loopback addresses
        
        Args:
            base_dir: Base directory for node overlays
            node_configs: Dict mapping node names to their global unique IDs
                         e.g., {'node1': 1, 'node2': 5, 'node3': 10}
        """
        _sysctl('net.ipv4.neigh.default.gc_thresh1', '4096')
        _sysctl('net.ipv4.neigh.default.gc_thresh2', '8192')
        _sysctl('net.ipv4.neigh.default.gc_thresh3', '16384')
        _sysctl('net.ipv4.fib_multipath_hash_policy', '1')
        _sysctl('net.ipv4.conf.all.rp_filter', '0')
        _sysctl('net.ipv6.neigh.default.gc_thresh1', '4096', check=False)
        _sysctl('net.ipv6.neigh.default.gc_thresh2', '8192', check=False)
        _sysctl('net.ipv6.neigh.default.gc_thresh3', '16384', check=False)
        _sysctl('net.ipv6.fib_multipath_hash_policy', '1', check=False)
        _sysctl('net.mpls.platform_labels', '10000', check=False)

        self.clean()
        os.makedirs(NETNS_DIR, exist_ok=True)
        
        for node_name, node_id in node_configs.items():
            node_dir = f"{base_dir}/overlay/{node_name}"
            os.makedirs(node_dir, exist_ok=True)
            self.nodes[node_name] = Node(node_name, node_dir, node_id=node_id)
            
        _switch_netns(os.getpid())
        return {
            name: (node.peer2link['lo'].ipv4.compressed, node.peer2link['lo'].ipv6.compressed)
            for name, node in self.nodes.items()
        }

    def add_link_intra_machine(self,
            name1: str, name2: str,
            src_ifidx:int, src_addr4: str, src_addr6: str,
            dst_ifidx:int, dst_addr4: str, dst_addr6,
            delay: str, bw: str, loss: str
        ):
        node1 = self.nodes.get(name1)
        node2 = self.nodes.get(name2)
        if node1 is None or node2 is None:
            return

        pynetlink.add_link_veth(node1.pid, src_ifidx, name2, node2.pid, dst_ifidx, name1, self._main_net_sock_fd)
        node1.register_if(name2, src_ifidx)
        node2.register_if(name1, dst_ifidx)
        node1.init_if(name2, src_addr4, src_addr6, delay, bw, loss)
        node2.init_if(name1, dst_addr4, dst_addr6, delay, bw, loss)

    def add_link_inter_machine(self,
            name1: str, name2: str,
            ifidx: int, remote_ip: str, addr4: str, addr6: str,
            delay: str, bw: str, loss: str
        ):
        node1 = self.nodes.get(name1)
        if node1 is None:
            return

        pynetlink.add_link_vxlan(
            node1.pid, name2,
            ifidx, ipaddress.ip_address(remote_ip).packed,
            self._main_net_sock_fd
        )
        node1.register_if(name2, ifidx)
        node1.init_if(name2, addr4, addr6, delay, bw, loss)

    def init_route_daemons(self, conf_path: str, nodes: str):
        conf_path = os.path.abspath(conf_path)
        ctl_path = os.path.join(os.path.dirname(conf_path), 'bird.ctl')
        if nodes == 'all':
            nodes_lst = self.nodes.keys()
        else:
            nodes_lst = nodes.split(',')

        for node_name in nodes_lst:
            node = self.nodes.get(node_name)
            if node is None:
                continue
            proc = node.run_command(('bird', '-c', conf_path, '-s', ctl_path))
            proc.wait()

    def set_static_route(self, src: str, dst: str, next_hop: str):
        src_node = self.nodes.get(src)
        dst_node = self.nodes.get(dst)
        next_hop_node = self.nodes.get(next_hop)
        if src_node is None or dst_node is None or next_hop_node is None:
            return

        dst_network = dst_node.peer2link['lo'].ipv4.network
        via_addr = next_hop_node.peer2link[src].ipv4.ip.packed
        src_node.modify_routes([
            (True, dst_network.network_address.packed, dst_network.prefixlen, next_hop, via_addr)
        ])

    def get_ping_command(self, src: str, dst: str, extra_args: List[str] = []):
        src_node = self.nodes.get(src)
        dst_node = self.nodes.get(dst)
        if src_node is None or dst_node is None:
            return None

        dst_addr = dst_node.peer2link['lo'].ipv4.ip.compressed
        return src_node, ('ping', '-c', '4', '-i', '0.01', *extra_args, dst_addr)

    def get_iperf_commands(self, src: str, dst: str, src_args: List[str] = [], dst_args: List[str] = []):
        src_node = self.nodes.get(src)
        dst_node = self.nodes.get(dst)
        if src_node is None or dst_node is None:
            return None

        src_addr = src_node.peer2link['lo'].ipv4.ip.compressed
        dst_addr = dst_node.peer2link['lo'].ipv4.ip.compressed
        return (
            (dst_node, ('iperf3', *dst_args, '-s', '-1', '-B', dst_addr)),
            (src_node, ('iperf3', *src_args, '-c', dst_addr, '-B', src_addr)),
        )

    def get_exec_command(self, node_name: str, cmd: str):
        node = self.nodes.get(node_name)
        if node is None:
            return None
        return node, ('sh', '-lc', cmd)

    def netlink(self, routes):
        for name, nlmsg in routes:
            node = self.nodes.get(name)
            if node is None:
                print('warning: ', name, 'not exists, netlink skipped')
                continue

            pynetlink.netlink_request(node.pid, nlmsg)

    def check_route(self, node_name: str):
        node = self.nodes.get(node_name)
        if node is None:
            return ''

        return subprocess.check_output(
            ('nsenter', '-n', '-t', str(node.pid), 'ip', 'route'),
            text=True
        )

    def damage(self, random_list: List[str]):
        for node_name in random_list:
            node = self.nodes.get(node_name)
            if node is None:
                print(f"Node {node_name} not found")
                continue
            
            _switch_netns(node.pid)
            for ifname, link in node.peer2link.items():
                if link.if_idx == 1:
                    continue
                pynetlink.if_down(ifname, node.socket_fd)

            self.damage_lst.append(node)

    def recover(self):
        if not self.damage_lst:
            return
        
        for node in self.damage_lst:
            _switch_netns(node.pid)
            
            for ifname, link in node.peer2link.items():
                if link.if_idx == 1:
                    continue
                try:
                    pynetlink.if_up(ifname, node.socket_fd)
                    pynetlink.modify_addr(
                        True, ifname, link.ipv6.ip.packed, link.ipv6.network.prefixlen, node.socket_fd
                    )
                except:
                    pass

        self.damage_lst.clear()

    def update_if(self, node_name: str, ifname: str, delay: str, bw: str, loss: str):
        node = self.nodes.get(node_name)
        if node is None:
            return

        node.update_if(ifname, delay, bw, loss)

    def del_if(self, node_name: str, ifname: str):
        node = self.nodes.get(node_name)
        if node is None:
            return

        node.del_if(ifname)
