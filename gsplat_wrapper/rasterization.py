import torch
import torch.nn as nn
from gsplat.rendering import rasterization, rasterization_2dgs
from .utils import fov2focal, SH2RGB
import math


# def get_intrinsics_for_gsplat(fx, fy, width, height):
#     return torch.tensor(
#         [
#             [fx, 0, width / 2],
#             [0, fy, height / 2],
#             [0, 0, 1],
#         ]
#     )
def get_intrinsics_for_gsplat(fx, fy, cx, cy):
    return torch.tensor(
        [
            [fx, 0, cx],
            [0, fy, cy],
            [0, 0, 1],
        ]
    )
    
    
class GaussianRasterizationSettings:
    def __init__(
        self,
        image_height:int,
        image_width:int,
        tanfovx:float,
        tanfovy:float,
        cx:float,
        cy:float,
        bg:torch.Tensor,
        scale_modifier:float,
        viewmatrix:torch.Tensor,
        # projmatrix:torch.Tensor,
        sh_degree:int,
        campos:torch.Tensor,
        prefiltered:bool,
        debug:bool,
    ):
        self.image_height = image_height
        self.image_width = image_width
        self.tanfovx = tanfovx
        self.tanfovy = tanfovy
        self.cx = cx
        self.cy = cy
        self.bg = bg
        self.scale_modifier = scale_modifier
        self.viewmatrix = viewmatrix
        # self.projmatrix = projmatrix
        self.sh_degree = sh_degree
        self.campos = campos
        self.prefiltered = prefiltered
        self.debug = debug


class GaussianRasterizer(nn.Module):
    def __init__(self, raster_settings):
        super(GaussianRasterizer, self).__init__()
        self.raster_settings = raster_settings
        self.twodgs = False
        
        self.image_height = raster_settings.image_height
        self.image_width = raster_settings.image_width
        self.tanfovx = raster_settings.tanfovx
        self.tanfovy = raster_settings.tanfovy
        self.cx = raster_settings.cx
        self.cy = raster_settings.cy
        self.bg = raster_settings.bg
        self.scale_modifier = raster_settings.scale_modifier
        self.viewmatrix = raster_settings.viewmatrix
        # self.projmatrix = raster_settings.projmatrix
        self.sh_degree = raster_settings.sh_degree
        self.campos = raster_settings.campos
        self.prefiltered = raster_settings.prefiltered
        self.debug = raster_settings.debug
        
        self.fx = fov2focal(2. * math.atan(self.tanfovx), self.image_width)
        self.fy = fov2focal(2. * math.atan(self.tanfovy), self.image_height)
        
        self.K = get_intrinsics_for_gsplat(
            self.fx, self.fy, 
            self.cx, self.cy
        )[None].to(self.viewmatrix.device)
        
        if len(self.bg.shape) == 1:
            self.bg = self.bg[None].repeat(self.K.shape[0], 1)
        
    def forward(
        self, means3D, means2D,
        shs, colors_precomp, opacities,
        scales, rotations, cov3D_precomp
        ):
        
        if colors_precomp is None:
            sh_degree = self.sh_degree
        else:
            sh_degree = None
        
        
        
        if self.twodgs:
            render_colors, render_alphas, normals, normals_from_depth, render_distort, render_median, info = rasterization_2dgs(
                means=means3D,
                quats=rotations / rotations.norm(dim=-1, keepdim=True),
                scales=scales,
                opacities=opacities[..., 0] if len(opacities.shape)>1 else opacities,
                colors=shs if colors_precomp is None else colors_precomp,
                sh_degree=sh_degree,
                viewmats=self.viewmatrix,
                Ks=self.K,
                width=self.image_width,
                height=self.image_height,
                backgrounds=self.bg,
                near_plane=0.01,  # TODO
                far_plane=1e10,  # TODO
                # eps2d=0.3,
                render_mode='RGB',  # 'RGB', 'D', 'ED', 'RGB+D', 'RGB+ED'
                # packed=False,
                absgrad=False,
                sparse_grad=False,
                # rasterize_mode='classic',  # 'classic', 'antialiased'
            )
        else:
            render_colors, render_alphas, info = rasterization(
                means=means3D,
                quats=rotations,
                scales=scales,
                opacities=opacities[..., 0] if len(opacities.shape)>1 else opacities,
                colors=shs if colors_precomp is None else colors_precomp,
                sh_degree=sh_degree,
                viewmats=self.viewmatrix,
                Ks=self.K,
                width=self.image_width,
                height=self.image_height,
                backgrounds=self.bg,
                near_plane=0.01,  # TODO
                far_plane=1e10,  # TODO
                # eps2d=0.3,
                render_mode='RGB',  # 'RGB', 'D', 'ED', 'RGB+D', 'RGB+ED'
                packed=False,
                absgrad=False,
                sparse_grad=False,
                rasterize_mode='classic',  # 'classic', 'antialiased'
            )
        
        rendered_image = render_colors[0].permute(2, 0, 1)  # [3, 1080, 1920]
        radii = info['radii']
        _means2d = info['means2d']
        means2D = _means2d[0] if _means2d.dim() > 2 else _means2d
        
        return rendered_image, radii
