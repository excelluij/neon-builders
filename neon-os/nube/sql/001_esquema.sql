-- Neon OS en la nube · 001 · tablas, perfil automático y rol no auto-asignable.
-- Se pega y ejecuta completo en Supabase → SQL Editor. Se puede repetir sin romper nada.

create table if not exists public.perfiles (
    id      uuid primary key references auth.users (id) on delete cascade,
    usuario text not null,
    rol     text not null default 'Estudiante' check (rol in ('Estudiante', 'Profesor', 'Administrador')),
    materia text,
    grado   text,
    creado  timestamptz not null default now()
);
-- «Ana» y «ana» son el mismo usuario
create unique index if not exists perfiles_usuario_unico on public.perfiles (lower(usuario));

create table if not exists public.misiones (
    id      bigint generated always as identity primary key,
    materia text not null,
    datos   jsonb not null,
    autor   uuid references public.perfiles (id) on delete set null
);

create table if not exists public.progreso (
    usuario_id uuid primary key references public.perfiles (id) on delete cascade,
    datos      jsonb not null default '{}'::jsonb,
    actualizado timestamptz not null default now()
);

create table if not exists public.ranking_ocultos (
    usuario_id uuid primary key references public.perfiles (id) on delete cascade
);

-- Seguridad por fila activada desde el principio: sin políticas (002) nadie con la clave pública puede leer ni escribir.
alter table public.perfiles        enable row level security;
alter table public.misiones        enable row level security;
alter table public.progreso        enable row level security;
alter table public.ranking_ocultos enable row level security;

-- Al registrarse alguien en Auth se crea su perfil. El rol SIEMPRE nace «Estudiante» y la materia vacía,
-- sin importar lo que mande el cliente en los metadatos: Profesor y Administrador se obtienen por otras vías (003).
create or replace function public.crear_perfil() returns trigger
language plpgsql security definer set search_path = public as $$
begin
    insert into public.perfiles (id, usuario, rol, materia, grado)
    values (
        new.id,
        coalesce(nullif(trim(new.raw_user_meta_data ->> 'usuario'), ''), split_part(new.email, '@', 1)),
        'Estudiante',
        null,
        nullif(trim(new.raw_user_meta_data ->> 'grado'), '')
    );
    return new;
end $$;

drop trigger if exists al_crear_usuario on auth.users;
create trigger al_crear_usuario after insert on auth.users
    for each row execute function public.crear_perfil();
