"""
A simple command-line interface for Starrynet.

The Starrynet CLI provides a simple control console which
makes it easy to control the network and have access to nodes. For example, the command

starrynet> create_nodes

simply starts the network nodes.

starrynet> get_neighbors 1, 5

gets the neighbors of node#1 at 5 second.

starrynet> set_ping 26 27 30

should work correctly and allow node#26 to ping node#26 at 30 second.

starrynet> set_perf 26 27 30

should work correctly and allow node#26 to perf node#26 at 30 second.

author: Yangtao Deng (dengyt21@mails.tsinghua.edu.cn)
"""

from subprocess import call
from cmd import Cmd
from os import isatty
from select import poll, POLLIN
import sys

from starrynet.log import info, output, error
# from starrynet.term import makeTerms, runX11
# from starrynet.util import ( quietRun, dumpNodeConnections,
#                            dumpPorts )


class CLI(Cmd):
    "Simple command-line interface to talk to nodes."

    prompt = 'starrynet> '

    def __init__(self, starrynet, stdin=sys.stdin, *args, **kwargs):
        """Start and run interactive or batch mode CLI
           starrynet: Starrynet network object
           stdin: standard input for CLI
           script: script to run in batch mode"""
        self.sn = starrynet
        # Local variable bindings for py command
        self.locals = {'net': starrynet}
        # Attempt to handle input
        self.inPoller = poll()
        self.inPoller.register(stdin)
        Cmd.__init__(self, *args, stdin=stdin, **kwargs)
        info('*** Starting CLI:\n')

        self.run()

    def run(self):
        "Run our cmdloop(), catching KeyboardInterrupt"
        while True:
            try:
                self.cmdloop()
                break
            except KeyboardInterrupt:
                # Output a message - unless it's also interrupted
                # pylint: disable=broad-except
                try:
                    output('\nInterrupt\n')
                except Exception:
                    pass
                # pylint: enable=broad-except

    def emptyline(self):
        "Don't repeat last command when you hit return."
        pass

    def getLocals(self):
        "Local variable bindings for py command"
        self.locals.update(self.mn)
        return self.locals

    helpStr = (
        'Supported commands are as follows:\n'
        '  starrynet> help\n'
        '  starrynet> create_nodes\n'
        '  starrynet> create_links\n'
        '  starrynet> run_routing_deamon\n'
        '  starrynet> get_distance 1 2 10\n'
        '   // It means getting the distance of two node (#1 and #2) at #10 second.\n'
        '  starrynet> get_neighbors 5 16\n'
        '   // It means getting the neighbor node indexes of node #5 at #16 second.\n'
        '  starrynet> get_GSes 7 20\n'
        '   // It means getting the connected GS node indexes of node #6 at #20 second.\n'
        '  starrynet> get_position 7 23 \n'
        '   // It means getting the LLA position of node #7 at #23 second.\n'
        '  starrynet> get_IP 8 \n'
        '   // It means getting the IP addresses of node #8. "create_nodes" and "create_links" must be runned before this.\n'
        '  starrynet> get_utility 27\n'
        '   // It means getting the memory and CPU utility information at #27 second. The output file will be generated at the working directory once the emulation starts.\n'
        '  starrynet> set_damage 0.3 30\n'
        '   // It means setting a random damage of a given ratio of 0.3 at #30 second, which will be processed during emulation.\n'
        '  starrynet> set_recovery 50\n'
        '   // It means setting a recovery of the damages at #50 second, which will be processed during emulation.\n'
        '  starrynet> check_routing_table 26 40\n'
        '   // It means listing the routing table of node #26 at #40 second. The output file will be written at the working directory.\n'
        '  starrynet> set_next_hop 1 26 2 45\n'
        '   // It means setting the next hop to node #2 for node #1 for the destination of node #26 at #45 second. Sat, Des and NextHopSat are indexes and Sat and NextHopSat are neighbors, which will be processed during emulation.\n'
        '  starrynet> set_ping 1 26 46\n'
        '   // It means pinging msg of from node #1 to node #26 at #46 second. The output file will be written at the working directory.\n'
        '  starrynet> set_perf 1 26 46\n'
        '   // It means perfing from node #1 to node #26 at #46 second. The perfing output file will be written at the working directory.\n'
        '  starrynet> start_emulation\n'
        '   // "create_nodes", "create_links" and "run_routing_deamon" must be runned before this.'
        '  starrynet> stop_emulation\n'
        '  starrynet> exit\n'
        '  starrynet> quit\n'
        '  starrynet> EOF\n'
        ' You may use the commands multiple times.\n')

    def do_help(self, line):
        "Describe available CLI commands."
        Cmd.do_help(self, line)
        if line == '':
            output(self.helpStr)

    def do_create_nodes(self, _line):
        "initialize the entire network nodes"
        self.sn.create_nodes()

    def do_create_links(self, _line):
        "initialize the entire network links"
        self.sn.create_links()

    def do_run_routing_deamon(self, _line):
        "run routing deamon for each node"
        self.sn.run_routing_deamon()

    def do_get_distance(self, line):
        "calculate the distance of two node at a certain time"
        arg, args, line = self.parseline(line)
        rest = line.split(' ')
        node_distance = self.sn.get_distance(int(rest[0]), int(rest[1]),
                                             int(rest[2]))
        output("The distance between node#%d and node#%d is %.2fkm.\n" %
               (int(rest[0]), int(rest[1]), node_distance))

    def do_get_neighbors(self, line):
        "list the neighbor node indexes of node at a certain time"
        arg, args, line = self.parseline(line)
        rest = line.split(' ')
        neighbors_index = self.sn.get_neighbors(int(rest[0]), int(rest[1]))
        output("The neighbors are: " + str(neighbors_index) + ".\n")

    def do_get_GSes(self, line):
        "list the GS connected to the node at a certain time"
        arg, args, line = self.parseline(line)
        rest = line.split(' ')
        GSes = self.sn.get_GSes(int(rest[0]), int(rest[1]))
        output("The connected GS(es) is(are): " + str(GSes) + ".\n")

    def do_get_position(self, line):
        "list the LLA of a node at a certain time"
        arg, args, line = self.parseline(line)
        rest = line.split(' ')
        LLA = self.sn.get_position(int(rest[0]), int(rest[1]))
        output("The LLA is: " + str(LLA))

    def do_get_IP(self, line):
        "list the IP of a node"
        arg, args, line = self.parseline(line)
        IP = self.sn.get_IP(int(arg))
        output("The IP list of the node is(are): " + str(IP) + ".\n")

    def do_get_utility(self, line):
        "list the CPU and memory useage at a certain time"
        "The output file will be generated once the emulation starts"
        arg, args, line = self.parseline(line)
        self.sn.get_utility(int(arg))

    def do_set_damage(self, line):
        "set a random damage of a given ratio at a certain time, which will be processed during emulation"
        arg, args, line = self.parseline(line)
        rest = line.split(' ')
        self.sn.set_damage(float(rest[0]), int(rest[1]))

    def do_set_recovery(self, line):
        "set a recovery of the damages at a certain time, which will be processed during emulation"
        arg, args, line = self.parseline(line)
        rest = line.split(' ')
        self.sn.set_recovery(int(rest[0]))

    def do_check_routing_table(self, line):
        "list the routing table of a node at a certain time."
        "The output file will be written at the working directory."
        arg, args, line = self.parseline(line)
        rest = line.split(' ')
        self.sn.check_routing_table(int(rest[0]), int(rest[1]))

    def do_set_next_hop(self, line):
        "set the nhelpext hop at a certain time"
        "Sat, Des and NextHopSat are indexes and Sat and NextHopSat are neighbors, which will be processed during emulation"
        arg, args, line = self.parseline(line)
        rest = line.split(' ')
        self.sn.set_next_hop(int(rest[0]), int(rest[1]), int(rest[2]),
                             int(rest[3]))

    def do_path(self, line):
        "get the working directory"
        output(self.sn.configuration_file_path + "\n")

    def do_set_ping(self, line):
        "ping msg of two nodes at a certain time"
        "The output file will be written at the working directory"
        arg, args, line = self.parseline(line)
        rest = line.split(' ')
        self.sn.set_ping(int(rest[0]), int(rest[1]), int(rest[2]))

    def do_set_perf(self, line):
        "perf msg of two nodes at a certain time"
        "The output file will be written at the working directory"
        arg, args, line = self.parseline(line)
        rest = line.split(' ')
        self.sn.set_perf(int(rest[0]), int(rest[1]), int(rest[2]))

    def do_start_emulation(self, _line):
        "start the emulation"
        self.sn.start_emulation()

    def do_stop_emulation(self, _line):
        "stop the emulation"
        self.sn.stop_emulation()
        return 'exited by user command'

    def do_exit(self, _line):
        "stop the emulation"
        self.sn.stop_emulation()
        return 'exited by user command'

    def do_quit(self, line):
        "Exit"
        return self.do_exit(line)

    def do_EOF(self, line):
        "Exit"
        output('\n')
        return self.do_exit(line)

    def default(self, line):
        "Exit"
        error('*** Unknown command: %s\n' % line)
        return
