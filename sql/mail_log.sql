create table mail_log (
    id serial primary key,
    message_id varchar(512) not null,
    r_date timestamp not null,
    d_date timestamp not null,
    dsn varchar(16) not null,
    relay_host varchar(256) not null,
    relay_port integer not null default 0,
    delay numeric not null default 0,
    status varchar(64) not null default 'N.D.',
    status_desc text not null default '',
    mailto varchar(256) not null default 'N.D.',
    ref varchar(256) not null default ''
);
create index idx_mail_log_message_id on mail_log (message_id);
create index idx_mail_log_r_date on mail_log (r_date);
create index idx_mail_log_d_date on mail_log (d_date);
create index idx_mail_log_relay_host on mail_log (relay_host);
create index idx_mail_log_mailto on mail_log (mailto);
create index idx_mail_log_ref on mail_log (ref);
