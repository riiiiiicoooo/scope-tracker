{ pkgs }:
{
  deps = [
    pkgs.nodejs_20
    pkgs.python311
    pkgs.postgresql_15
    pkgs.git
    pkgs.gnumake
    pkgs.jq
  ];

  env = {
    LD_LIBRARY_PATH = "${pkgs.lib.makeLibraryPath [pkgs.postgresql_15]}";
    PGHOST = "/tmp";
    PGDATA = "/tmp/postgres";
  };

  bootstrap = ''
    # Initialize PostgreSQL for local development
    if [ ! -d "$PGDATA" ]; then
      mkdir -p "$PGDATA"
      initdb -D "$PGDATA" --auth=trust --username=user
    fi

    # Start PostgreSQL in background
    pg_ctl -D "$PGDATA" -l "$PGDATA/logfile" start || true
    sleep 2

    # Create database
    createdb -U user scope_tracker 2>/dev/null || true

    # Install Node dependencies
    npm install

    # Run Supabase migrations
    npm run db:migrate
  '';
}
