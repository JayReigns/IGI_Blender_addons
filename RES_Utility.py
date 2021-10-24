
bl_info = {
    "name": "RES Utility",
    "author": "JayReigns",
    "version": (1, 0, 0),
    "blender": (2, 8, 0),
    "location": "Text Editor > ToolBar > Text Panel",
    "description": "",
    "category": "Development"
}

import bpy, struct, os, math


def parse_res(path, context):
    
    with open(path, 'rb') as file:
    
        if file.read(4) != b'ILFF': raise ValueError("Unknown File Type!")
            
        unpack = struct.Struct('<3I').unpack
            
        size, version, next_offset = unpack(file.read(12))
        
        if file.read(4) != b'IRES': raise ValueError("Bad File Format!")
        
        res_props = context.scene.res_props
        res_props.path = path
        res_props.active_item = -1
        res_props.prefix = ''
        res_props.items.clear()
        
        while True:
            
            soffset = file.tell()
            boffset = soffset
            
            if file.read(4) != b'NAME': raise ValueError("Bad File Format!")
            
            size, ver, noffs = unpack(file.read(12))
            ipath = str(file.read(size), 'ascii')
            boffset += noffs
            file.seek(boffset)
            
            if file.read(4) != b'BODY': raise ValueError("Bad File Format!")
            
            size, ver, noffs = unpack(file.read(12))
            offset = file.tell()
            boffset += noffs
            file.seek(boffset)
            
            prefix, name = ipath.rsplit('/', 1)
            
            if res_props.prefix == '': res_props.prefix = prefix
            
            item = res_props.items.add()
            item.name = name
            item.soffset = soffset
            item.offset = offset
            item.size = size
            
            if noffs == 0: break
        
    return


def export_item(path, context):
    
    res_props = context.scene.res_props
    
    if res_props.active_item == -1: return
    
    item = res_props.items[res_props.active_item]
    
    with open(res_props.path, 'rb') as file:
        file.seek(item.offset)
        data = file.read(item.size)
    
    with open(path, 'wb') as file:
        file.write(data)
        
    return


def RES_write_bytes(name, data, file, end=False):
    size = len(data)
    align = math.ceil(size/4)*4
    file.write(name)
    file.write(struct.pack('<3I', size, 4, 0 if end else align+16))
    file.write(data)
    if (align - size) > 0: file.write(bytes([0]*(align - size)))
    return

def RES_remove_item_entry(idx, file, res_props):
    
    if idx == 0 and len(res_props.items) > 1:
        # seek to 2nd item and place name block to start and overwrite next_offset
        # TODO: if only 1 item in RES file
        file.seek(res_props.items[0].offset - 4)
        file.seek(struct.unpack('<I', file.read(4))[0] -16, 1)
        
        block_offset = file.tell()
        file.seek(12, 1)
        block_size = struct.unpack('<I', file.read(4))[0]
        print(block_offset, block_size)
        
        # read NAME block
        file.seek(block_offset)
        data = file.read(block_size)
        
        # write NAME block
        file.seek(20)  # seeks to start
        file.write(data)
        
        # write next_offset
        file.seek(20 + 12)
        file.write(struct.pack('<I', block_offset+block_size-20))
        
    elif idx > 0:
        
        cur_item = res_props.items[idx]
        
        # get next block abs offset
        file.seek(cur_item.offset - 4)
        next_offset = struct.unpack('<I', file.read(4))[0] - 16 + cur_item.offset
        
        prev_item = res_props.items[idx-1]
        # goto prev BODY block and overwrite next_offset
        file.seek(prev_item.offset - 4)
        file.write(struct.pack('<I', next_offset - prev_item.offset + 16))
    
    if idx == len(res_props.items)-1:
        # set last block next_offset to zero
        file.seek(res_props.items[-2].offset-4)
        file.write(struct.pack('<I', 0))
    
    if idx!= -1: res_props.items.remove(idx)
    
    return

def RES_append_item(path, file, res_props):
    
    if len(res_props.items) > 0:
        # set next_offset to prev block
        last_item = res_props.items[-1]
        aligned_size = math.ceil(last_item.size/4)*4
        file.seek(last_item.offset - 4)
        file.write(struct.pack('<I', aligned_size + 16))
        file.seek(aligned_size, 1)
    else:
        file.seek(20)
    
    # write NAME block
    data = bytes(res_props.prefix + '/' + path.rsplit(os.sep, 1)[1] + '\0', 'utf-8')
    RES_write_bytes(b'NAME', data, file)
    
    # write BODY block
    with open(path, 'rb') as f: data = f.read()
    RES_write_bytes(b'BODY', data, file, end=True)
    
    # set the size of main block
    fsize = file.tell()
    file.seek(4)
    file.write(struct.pack('<I', fsize))
    
    return

def RES_add_replace_item(path, context):
    
    res_props = context.scene.res_props
    
    with open(res_props.path, 'r+b') as file:
        
        # get file name
        name = path.rsplit(os.sep, 1)[1]
        
        idx = res_props.items.find(name)
        
        RES_remove_item_entry(idx, file, res_props)
        
        RES_append_item(path, file, res_props)
    
    parse_res(res_props.path, context)
    return

def RES_remove_item(context):
    
    res_props = context.scene.res_props
    
    if res_props.active_item < 0: return
    
    with open(res_props.path, 'r+b') as file:
        
        RES_remove_item_entry(res_props.active_item, file, res_props)
        
        if len(res_props.items) == 1:
            # no items left after deletion
            file.seek(4)
            file.write(struct.pack('<I', 20))
    
    parse_res(res_props.path, context)
    return

#########################################################################################

"""Operators"""

from bpy.types import Operator
from bpy_extras.io_utils import ImportHelper, ExportHelper
from bpy.props import StringProperty


class RES_OT_OpenFile(Operator, ImportHelper):

    bl_idname = "res.open_file"
    bl_label = "Open .res file"
    bl_options = {'PRESET', 'UNDO'}
    
    filter_glob: StringProperty(
        default='*.res;*.RES',
        options={'HIDDEN'}
    )
    
    def execute(self, context):
        
        parse_res(self.filepath, context)
        return {'FINISHED'}

class RES_OT_ReloadFile(Operator):

    bl_idname = "res.reload_file"
    bl_label = "Reload .res file"
    bl_options = {'PRESET', 'UNDO'}
    
    def execute(self, context):
        
        parse_res(context.scene.res_props.path, context)
        return {'FINISHED'}

class RES_OT_ExportItem(Operator, ExportHelper):

    bl_idname = "res.export_item"
    bl_label = "Export"
    bl_options = {'PRESET', 'UNDO'}
    
    filename_ext = ""
    
    filter_glob: StringProperty(
        options={'HIDDEN'}
    )
    
    def invoke(self, context, _event):
        
        res_props = context.scene.res_props
        
        if res_props.active_item == -1:
            return {'FINISHED'}
        
        name, ext = res_props.items[res_props.active_item].name.rsplit('.', 1)
        
        self.filename_ext = f".{ext}"
        
        if not self.filepath:
            blend_filepath = context.blend_data.filepath
            if not blend_filepath:
                blend_filepath = name
            else:
                blend_filepath = os.path.splitext(blend_filepath)[0]

            self.filepath = os.path.join(blend_filepath, name)
        
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
    
    def execute(self, context):
        
        export_item(self.filepath, context)
        
        return {'FINISHED'}


class RES_OT_AddReplace(Operator, ImportHelper):

    bl_idname = "res.add_replace_item"
    bl_label = "Add/Replace Item"
    bl_options = {'PRESET', 'UNDO'}
    
    def execute(self, context):
        
        RES_add_replace_item(self.filepath, context)
        return {'FINISHED'}


class RES_OT_Remove(Operator):

    bl_idname = "res.remove_item"
    bl_label = "Remove Item"
    bl_options = {'PRESET', 'UNDO'}
    
    def execute(self, context):
        
        RES_remove_item(context)
        return {'FINISHED'}


class RES_OT_DUMMY(Operator):

    bl_idname = "res.dummy"
    bl_label = ""
    
    def execute(self, context):
        return {'FINISHED'}

#########################################################################################

"""UI Panels"""

from bpy.types import Panel

class RES_PT_Browser(Panel):
    bl_idname = 'RES_PT_api_browser'
    bl_space_type = "TEXT_EDITOR"
    bl_region_type = "UI"
    bl_label = "RES Browser"
    bl_options = {'DEFAULT_CLOSED'}
    bl_category = "Text"
    
    def draw(self, context):
        
        res_props = context.scene.res_props
        
        layout = self.layout
        
        col = layout.column()
        
        row = col.row(align=True)
        if res_props.path == '':
            label = RES_OT_OpenFile.bl_label
        else:
            label = res_props.path
        row.operator(RES_OT_OpenFile.bl_idname, text=label, icon="FILEBROWSER")
        row.operator(RES_OT_ReloadFile.bl_idname, text='', icon="FILE_REFRESH")
        
        col.template_list("UI_UL_list", "res_itrm_list", res_props, "items", res_props, "active_item")
        
        col = layout.column(align=True)
        
        col.operator(RES_OT_AddReplace.bl_idname, text=RES_OT_AddReplace.bl_label, icon="IMPORT")
        col.operator(RES_OT_ExportItem.bl_idname, text=RES_OT_ExportItem.bl_label, icon="EXPORT")
        col.operator(RES_OT_Remove.bl_idname, text=RES_OT_Remove.bl_label, icon="X")


#########################################################################################

"""Properties"""

from bpy.types import PropertyGroup
from bpy.props import StringProperty, IntProperty, BoolProperty, CollectionProperty, PointerProperty

class RES_Item(PropertyGroup):

    name : StringProperty( name="Name", description="Item Name", default="Untitled")
    offset : IntProperty(name='offset', description='offset', default=-1)
    size : IntProperty(name='size', description='size', default=0)
    soffset : IntProperty(name='boffset', description='block offset', default=-1)

class RES_Props(PropertyGroup):
    
    path : StringProperty(name='path', description='.res path', default='')
    prefix : StringProperty(name='path', description='.res path', default='')
    active_item : IntProperty(name='active_item', description='active item', default=-1)
    items : CollectionProperty(type = RES_Item)


#########################################################################################

classes = (
    RES_OT_OpenFile,
    RES_OT_ReloadFile,
    RES_OT_ExportItem,
    RES_OT_AddReplace,
    RES_OT_Remove,
    RES_OT_DUMMY,
    
    RES_PT_Browser,
    
    RES_Item,
    RES_Props,

)

def register():
    
    for cls in classes: bpy.utils.register_class(cls)
    bpy.types.Scene.res_props = PointerProperty(type=RES_Props, name='RES Props', description='')


def unregister():
    
    del bpy.types.Scene.res_props
    for cls in reverse(classes): bpy.utils.unregister_class(cls)


if __name__ == '__main__':
    register()
