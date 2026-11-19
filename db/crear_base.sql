-- Crea el usuario y la base de datos del panel. Se ejecuta como «postgres» con db\crear_base.ps1,
-- que pasa estas variables desde DATABASE_URL del archivo .env:
--   :usuario  :clave  :base
-- Se puede ejecutar varias veces: si ya existen, solo actualiza la contraseña.

SELECT format('CREATE ROLE %I LOGIN', :'usuario')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'usuario') \gexec

SELECT format('ALTER ROLE %I WITH LOGIN PASSWORD %L', :'usuario', :'clave') \gexec

SELECT format('CREATE DATABASE %I OWNER %I ENCODING %L TEMPLATE template0', :'base', :'usuario', 'UTF8')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'base') \gexec

-- Solo el dueño (el panel) puede conectarse a la base
SELECT format('REVOKE ALL ON DATABASE %I FROM PUBLIC', :'base') \gexec
SELECT format('GRANT ALL ON DATABASE %I TO %I', :'base', :'usuario') \gexec
