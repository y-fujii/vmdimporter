# VMD (Vocaloid Motion Data) importer for Blender 2.5
# by y.fujii <y-fujii at mimosa-pudica.net>, public domain
#
# Usage:
#     0. Copy this file to "scripts/addons/".
#     1. If you have MeshIO, make sure that its directory name is "meshio".
#        It is used for Japanese-to-English mapping of the bone and shape key names.
#     2. Run the Blender and enable "Import Vocaloid Motion Data (.vmd)" add-on.
#     3. Load your favorite model.
#     4. Select the armature and/or the object which has shape keys.
#     5. Click the menu "File > Import > Vocaloid Motion Data (.vmd)".
#
# Thanks for analyzing & providing information about VMD file format:
#     - http://atupdate.web.fc2.com/vmd_format.htm
#     - http://blog.goo.ne.jp/torisu_tetosuki/e/bc9f1c4d597341b394bd02b64597499d
#     - http://harigane.at.webry.info/201103/article_1.html
#
# This program can be used with excellent MMD importer "MeshIO":
#     - http://sourceforge.jp/projects/meshio/

import io
import struct
import mathutils
import bpy
import bpy_extras
try:
	from meshio.pymeshio import englishmap
	boneNameMap = { t[1]: t[0] for t in englishmap.boneMap }
	faceNameMap = { t[1]: t[0] for t in englishmap.skinMap }
except:
	print( "MeshIO is not found." )
	boneNameMap = {}
	faceNameMap = {}


bl_info = {
	"name": "Import Vocaloid Motion Data (.vmd)",
	"category": "Import-Export",
}


def readPacked( ofs, fmt ):
	return struct.unpack( fmt, ofs.read( struct.calcsize( fmt ) ) )

def vmdStr( s ):
	i = s.index( b"\0" )
	return str( s[:i], "shift-jis" )

def importVmdBone( ofs, obj, offset ):
	baseRot = { b.name: b.matrix_local.to_quaternion() for b in obj.data.bones }

	frameEnd = offset
	size, = readPacked( ofs, "< I" )
	for _ in range( size ):
		name, frame, tx, ty, tz, rx, ry, rz, rw, _ = readPacked( ofs, "< 15s I 3f 4f 64s" )
		name = vmdStr( name )
		name = boneNameMap.get( name, name )
		frame += offset
		if name in obj.pose.bones:
			bone = obj.pose.bones[name]
			bone.location = mathutils.Vector( (tx, tz, ty) )
			# transform basis of rotation
			bone.rotation_quaternion = (
				baseRot[name].conjugated() *
				mathutils.Quaternion( (rw, -rx, -rz, -ry) ) *
				baseRot[name]
			)
			bone.keyframe_insert( "location", frame = frame )
			bone.keyframe_insert( "rotation_quaternion", frame = frame )

		frameEnd = max( frameEnd, frame )
	
	return frameEnd

def skipVmdBone( ofs ):
	size, = readPacked( ofs, "< I" )
	ofs.seek( struct.calcsize( "< 15s I 3f 4f 64s" ) * size, 1 )

def importVmdFace( ofs, obj, offset ):
	frameEnd = offset
	size, = readPacked( ofs, "< I" )
	for _ in range( size ):
		name, frame, value = readPacked( ofs, "< 15s I f" )
		name = vmdStr( name )
		name = faceNameMap.get( name, name )
		frame += offset
		if name in obj.data.shape_keys.key_blocks:
			block = obj.data.shape_keys.key_blocks[name]
			block.value = value
			block.keyframe_insert( "value", frame = frame )

		frameEnd = max( frameEnd, frame )

	return frameEnd

def skipVmdFace( ofs ):
	size, = readPacked( ofs, "< I" )
	ofs.seek( struct.calcsize( "< 15s I f" ) * size, 1 )

def importVmd( ofs, bone, face, offset = 0 ):
	magic, name = readPacked( ofs, "< 30s 20s" )
	magic = vmdStr( magic )
	#name = vmdStr( name )
	if not magic.startswith( "Vocaloid Motion Data" ):
		raise IOError()

	if bone:
		fe0 = importVmdBone( ofs, bone, offset )
	else:
		skipVmdBone( ofs )
		fe0 = offset

	if face:
		fe1 = importVmdFace( ofs, face, offset )
	else:
		skipVmdFace( ofs )
		fe1 = offset

	bpy.context.scene.frame_end = max( fe0, fe1, bpy.context.scene.frame_end )

# UI

class VmdImporter( bpy.types.Operator, bpy_extras.io_utils.ImportHelper ):
	bl_idname    = "import_anim.vmd"
	bl_label     = "Import VMD"
	filename_ext = ".vmd"
	filter_glob  = bpy.props.StringProperty( default = "*.vmd", options = { "HIDDEN" } )
	frame_offset = bpy.props.IntProperty( name = "Frame offset", default = 1 )

	def execute( self, ctx ):
		for obj in bpy.context.selected_objects:
			if hasattr( obj.data, "bones" ) and obj.data.bones:
				bone = obj
				break
		else:
			bone = None

		for obj in bpy.context.selected_objects:
			if hasattr( obj.data, "shape_keys" ) and obj.data.shape_keys:
				face = obj
				break
		else:
			face = None

		with io.FileIO( self.filepath ) as ofs:
			importVmd( ofs, bone, face, self.frame_offset )

		return { "FINISHED" }

def menu_func( self, ctx ):
	self.layout.operator( VmdImporter.bl_idname, text = "Vocaloid Motion Data (.vmd)" )

def register():
	bpy.utils.register_class( VmdImporter )
	bpy.types.INFO_MT_file_import.append( menu_func )

def unregister():
	bpy.utils.unregister_class( VmdImporter )
	bpy.types.INFO_MT_file_import.remove( menu_func )

if __name__ == "__main__":
	register()
