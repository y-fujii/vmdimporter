# VMD (Vocaloid Motion Data) importer for Blender 2.5+
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
#     - http://d.hatena.ne.jp/ousttrue/20100405/1270465133
#
# This program can be used with excellent PMD importer "MeshIO":
#     - http://sourceforge.jp/projects/meshio/
#
# Thanks for reporting bugs & sending patches:
#     - Thibaud de Souza (Tea for Anime 3D SFX)

import io
import struct
import collections
import mathutils
import sys
import bpy
import bpy_extras
try:
	from meshio.pymeshio import englishmap
	boneNameMap = { t[1]: t[0] for t in englishmap.boneMap }
	faceNameMap = { t[1]: t[0] for t in englishmap.skinMap }
except:
	sys.stderr.write( "MeshIO is not found.\n" )
	sys.stderr.flush()
	boneNameMap = {}
	faceNameMap = {}


bl_info = {
	"name": "Import Vocaloid Motion Data (.vmd)",
	"category": "Import-Export",
}


def choice1( it, cond ):
	for e in it:
		if cond( e ):
			return e
	return None

def readPacked( ofs, fmt ):
	return struct.unpack( fmt, ofs.read( struct.calcsize( fmt ) ) )


class VmdLoader( object ):

	@classmethod
	def loadStr( cls, s ):
		i = s.index( b"\0" )
		return str( s[:i], "cp932" )

	@classmethod
	def loadBone( cls, ofs, obj, offset ):
		timeEnd = 0
		data = collections.defaultdict( list )
		size, = readPacked( ofs, "< I" )
		for _ in range( size ):
			name, time, tx, ty, tz, rx, ry, rz, rw, _ = readPacked( ofs, "< 15s I 3f 4f 64s" )
			name = cls.loadStr( name )
			loc = mathutils.Vector( (tx, tz, ty) )
			rot = mathutils.Quaternion( (rw, -rx, -rz, -ry) )
			data[name].append( (time, loc, rot) )
			timeEnd = max( timeEnd, time )

		for name, frames in data.items():
			name = boneNameMap.get( name, name )
			if not name in obj.pose.bones:
				continue

			frames.sort()
			bone = obj.pose.bones[name]
			bone.rotation_mode = "QUATERNION"
			baseRot = bone.bone.matrix_local.to_quaternion()
			prevRot = mathutils.Quaternion( (1.0, 0.0, 0.0, 0.0) )
			for (time, loc, rot) in frames:
				# quaternion q and -q represent the same rotation,
				# we choose the nearer one to the previous one
				if prevRot.dot( rot ) < 0.0:
					rot = -rot
				prevRot = rot

				bone.location = loc
				# transform basis of rotation
				bone.rotation_quaternion = baseRot.conjugated() * rot * baseRot
				bone.keyframe_insert( "location",            frame = time + offset )
				bone.keyframe_insert( "rotation_quaternion", frame = time + offset )
		
		return timeEnd + offset

	@classmethod
	def skipBone( cls, ofs ):
		size, = readPacked( ofs, "< I" )
		ofs.seek( struct.calcsize( "< 15s I 3f 4f 64s" ) * size, 1 )

	@classmethod
	def loadFace( cls, ofs, obj, offset ):
		timeEnd = 0
		size, = readPacked( ofs, "< I" )
		for _ in range( size ):
			name, time, value = readPacked( ofs, "< 15s I f" )
			name = cls.loadStr( name )
			name = faceNameMap.get( name, name )
			if name in obj.data.shape_keys.key_blocks:
				block = obj.data.shape_keys.key_blocks[name]
				block.value = value
				block.keyframe_insert( "value", frame = time + offset )

			timeEnd = max( timeEnd, time )

		return timeEnd + offset

	@classmethod
	def skipFace( cls, ofs ):
		size, = readPacked( ofs, "< I" )
		ofs.seek( struct.calcsize( "< 15s I f" ) * size, 1 )

	@classmethod
	def load( cls, ofs, bone, face, offset = 0 ):
		magic, name = readPacked( ofs, "< 30s 20s" )
		magic = cls.loadStr( magic )
		#name = cls.loadStr( name )
		if not magic.startswith( "Vocaloid Motion Data" ):
			raise IOError()

		if bone:
			fe0 = cls.loadBone( ofs, bone, offset )
		else:
			cls.skipBone( ofs )
			fe0 = offset

		if face:
			fe1 = cls.loadFace( ofs, face, offset )
		else:
			cls.skipFace( ofs )
			fe1 = offset

		return max( fe0, fe1 )


class VmdImporterUi( bpy.types.Operator, bpy_extras.io_utils.ImportHelper ):
	bl_idname    = "import_anim.vmd"
	bl_label     = "Import VMD"
	filter_glob  = bpy.props.StringProperty( default = "*.vmd", options = { "HIDDEN" } )
	frame_offset = bpy.props.IntProperty( name = "Frame offset", default = 1 )

	def execute( self, ctx ):
		bone = choice1( bpy.context.selected_objects, lambda obj:
			hasattr( obj.data, "bones" ) and obj.data.bones
		)
		face = choice1( bpy.context.selected_objects, lambda obj:
			hasattr( obj.data, "shape_keys" ) and obj.data.shape_keys
		)

		with io.FileIO( self.filepath ) as ofs:
			frameEnd = VmdLoader.load( ofs, bone, face, self.frame_offset )
			bpy.context.scene.frame_end = max( frameEnd, bpy.context.scene.frame_end )

		return { "FINISHED" }


def menuFunc( self, ctx ):
	self.layout.operator( VmdImporterUi.bl_idname, text = "Vocaloid Motion Data (.vmd)" )

def register():
	bpy.utils.register_class( VmdImporterUi )
	bpy.types.INFO_MT_file_import.append( menuFunc )

def unregister():
	bpy.utils.unregister_class( VmdImporterUi )
	bpy.types.INFO_MT_file_import.remove( menuFunc )

if __name__ == "__main__":
	register()
