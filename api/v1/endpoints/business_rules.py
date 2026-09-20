"""HTTP routes for the business rules settings, mounted at /api/ajustes.

Every route is authenticated and takes the organization FROM THE TOKEN. These
write the rules the bot obeys — when it is open, how many cars fit, how long a
service takes — so a caller must never be able to name someone else's tenant.
That is why there is no organization_id parameter anywhere here: not optional,
absent.

Follows the shape of endpoints/citas.py.
"""

from datetime import date
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.deps import get_current_user
from schemas.business_rules import (
    AjustesRead,
    DiaEspecialCreate,
    HorarioSemanal,
    ServicioCreate,
    ServicioRead,
    ServicioUpdate,
)
from services import business_rules_service

router = APIRouter()


def require_organization_id(current_user: dict) -> str:
    """El tenant sale del token del llamador, nunca del request.

    get_current_user devuelve un usuario sin organización cuando falta su fila
    en app_users (ver api/deps.py); ese usuario no puede tocar ajustes.
    """
    organization_id = current_user.get("organization_id")
    if not organization_id:
        raise HTTPException(
            status_code=403, detail="El usuario no pertenece a una organización"
        )
    return str(organization_id)


@router.get(
    "",
    response_model=AjustesRead,
    summary="Leer los ajustes del negocio",
    tags=["ajustes"],
)
async def leer_ajustes(current_user: dict = Depends(get_current_user)) -> AjustesRead:
    """Horario, servicios y días especiales, en una sola llamada.

    Una sola respuesta porque la pantalla los muestra juntos: tres viajes para
    pintar una pantalla es latencia sin nada a cambio.
    """
    datos = await business_rules_service.leer_ajustes(
        require_organization_id(current_user)
    )
    return AjustesRead(**datos)


@router.put(
    "/horario",
    status_code=status.HTTP_200_OK,
    summary="Guardar el horario de atención",
    tags=["ajustes"],
)
async def guardar_horario(
    horario: HorarioSemanal,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Guarda la semana completa.

    La semana entera y no un día suelto: la pantalla edita los siete a la vez, y
    guardar de a uno deja al taller con medio horario si algo falla a la mitad.
    """
    await business_rules_service.guardar_horario(
        require_organization_id(current_user), horario
    )
    return {"guardado": len(horario.dias)}


@router.post(
    "/servicios",
    response_model=ServicioRead,
    status_code=status.HTTP_201_CREATED,
    summary="Agregar un tipo de servicio",
    tags=["ajustes"],
)
async def crear_servicio(
    servicio: ServicioCreate,
    current_user: dict = Depends(get_current_user),
) -> ServicioRead:
    """Alta de un servicio. Su duración decide si una cita cabe antes del cierre."""
    fila = await business_rules_service.crear_servicio(
        require_organization_id(current_user), servicio
    )
    return ServicioRead(**fila)


@router.patch(
    "/servicios/{servicio_id}",
    response_model=ServicioRead,
    summary="Cambiar un tipo de servicio",
    tags=["ajustes"],
)
async def actualizar_servicio(
    servicio_id: UUID,
    cambios: ServicioUpdate,
    current_user: dict = Depends(get_current_user),
) -> ServicioRead:
    """Renombrar, cambiar la duración, reordenar o desactivar.

    Desactivar y no borrar: `citas.service_type_id` apunta aquí, y borrar un
    servicio le dejaría a una cita vieja la duración del mínimo sin que nadie
    se entere.
    """
    fila = await business_rules_service.actualizar_servicio(
        require_organization_id(current_user), str(servicio_id), cambios
    )
    if fila is None:
        raise HTTPException(status_code=404, detail="El servicio no existe")
    return ServicioRead(**fila)


@router.post(
    "/dias-especiales",
    status_code=status.HTTP_200_OK,
    summary="Agregar o cambiar un feriado / horario especial",
    tags=["ajustes"],
)
async def guardar_dia_especial(
    dia: DiaEspecialCreate,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Una fecha concreta que pisa el horario semanal."""
    await business_rules_service.guardar_dia_especial(
        require_organization_id(current_user), dia
    )
    return {"fecha": dia.date.isoformat(), "abierto": dia.is_open}


@router.delete(
    "/dias-especiales/{fecha}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Quitar un feriado / horario especial",
    tags=["ajustes"],
)
async def borrar_dia_especial(
    fecha: date,
    current_user: dict = Depends(get_current_user),
) -> None:
    """Quitar la excepción devuelve el día a lo que diga el horario semanal."""
    borrado = await business_rules_service.borrar_dia_especial(
        require_organization_id(current_user), fecha
    )
    if not borrado:
        raise HTTPException(status_code=404, detail="Esa fecha no tiene excepción")


@router.post(
    "/dias-especiales/feriados",
    status_code=status.HTTP_200_OK,
    summary="Cargar los feriados de Panamá de un año",
    tags=["ajustes"],
)
async def cargar_feriados(
    anio: int = Query(..., ge=2020, le=2100, description="Año a cargar"),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Carga el calendario nacional del año, sin pisar lo ya ajustado a mano.

    El año es obligatorio: adivinar el actual cargaría feriados ya pasados sin
    que nadie lo pidiera.
    """
    agregados = await business_rules_service.cargar_feriados(
        require_organization_id(current_user), anio
    )
    return {"agregados": agregados}
