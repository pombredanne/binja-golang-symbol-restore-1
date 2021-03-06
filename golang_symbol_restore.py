#!/usr/bin/env python3

import struct

import binaryninja
from binaryninja.log import log_error, log_info


def find_gopclntab_section(view: binaryninja.binaryview.BinaryView) -> int:
    
    for section in view.sections.values():
        if section.name == ".gopclntab":
            return section.start
    else:
        magic_bytes_expected = "\xfb\xff\xff\xff\x00\x00"
        magic_bytes_found = view.find_next_data(0,magic_bytes_expected)
        if magic_bytes_found is None:
            return 0
    print("found .gopclntab at %x"%magic_bytes_found)
    return magic_bytes_found


def get_pointer_LE(view: binaryninja.binaryview.BinaryView, addr: int) -> bytes:
    addr_size = view.address_size
    return struct.unpack("<Q", view.read(addr, addr_size))[0]


def get_dword_LE(view: binaryninja.binaryview.BinaryView, addr: int) -> bytes:
    return struct.unpack("<I", view.read(addr, 4))[0]


def restore_symbols(view: binaryninja.binaryview.BinaryView,
                    addr: int) -> None:
    ptr_size = view.address_size

    """
    the .gopclntab table (starting at .gopclntab + 8) consists of
        N pc0 func0 pc1 func1 pc2 func2 ... pc(N-1) func(N-1) pcN
        
        N := no of elemements in table
        pcX := pointer to the function
        funcX := pointer to struct Func
        
        struct Func {
                uintptr entry;   // start pc
                int32 name;      // name (offset to C string)
                int32 args;      // size of arguments passed to function
                int32 frame;     // size of function frame, including saved caller PC
                int32 pcsp;      // pcsp table (offset to pcvalue table)
                int32 pcfile;    // pcfile table (offset to pcvalue table)
                int32 pcln;      // pcln table (offset to pcvalue table)
                int32 nfuncdata; // number of entries in funcdata list
                int32 npcdata;   // number of entries in pcdata list
        }; 
    src: https://docs.google.com/document/d/1lyPIbmsYbXnpNj57a261hgOYVpNRcgydurVQIyZOz_o/pub
    """
    # validate magic bytes
    magic_bytes_found = view.read(addr, 4)
    magic_bytes_expected = b'\xfb\xff\xff\xff'
    if magic_bytes_expected != magic_bytes_found:
        log_error("Invalid .gopclntab section. Aborting!")
        return

    # get number of elements and calculate last address
    size_addr = addr + 8  # skip first 8 bytes
    size = get_pointer_LE(view, size_addr)
    start_addr = size_addr + ptr_size
    end_addr = addr + 8 + ptr_size + (size * ptr_size * 2)

    # iterate over the table and restore function names
    for current_addr in range(start_addr, end_addr, 2 * ptr_size):
        function_addr = get_pointer_LE(view, current_addr)
        struct_func_offset = get_pointer_LE(view, current_addr + ptr_size)
        name_str_offset = get_dword_LE(view, addr + struct_func_offset + ptr_size)
        name_addr = addr + name_str_offset
        function_name = view.get_ascii_string_at(name_addr)
        if not function_name:
            continue
        log_info(f'found name "{function_name}" for function starting at 0x{function_addr:x}')
        function = view.get_function_at(function_addr)
        if not function:
            view.create_user_function(function_addr)
            function = view.get_function_at(function_addr)
        function.name = function_name.value


def restore_golang_symbols(view: binaryninja.binaryview.BinaryView):
    # for section in view.sections.values():
    gopclntab_start = find_gopclntab_section(view)
    if gopclntab_start != 0:
        restore_symbols(view,gopclntab_start)
    else:
        log_error("Could not find .gopclntab section. "
                  "If this is really a Golang binary you can annotate "
                  "the section manually by naming it '.gopclntab'")


