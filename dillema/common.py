from . import __version__

BANNER = r"""
 (            (      (               *               
 )\ )         )\ )   )\ )          (  `       (      
(()/(    (   (()/(  (()/(     (    )\))(      )\     
 /(_))   )\   /(_))  /(_))   ))\  ((_)()\  ((((_)(   
(_))_   ((_) (_))   (_))    /((_) (_()((_)  )\ _ )\  
 |   \   (_) | |    | |    (_))   |  \/  |  (_)_\(_) 
 | |) |  | | | |__  | |__  / -_)  | |\/| |   / _ \   
 |___/   |_| |____| |____| \___|  |_|  |_|  /_/ \_\                                                      
"""

# Define the custom banner
def print_banner():
    print(BANNER)

    
def get_ip_address():
    """
    Get the IP address of the current machine.
    """
    import socket
    return socket.gethostbyname(socket.gethostname())

