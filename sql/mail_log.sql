create table mail_log (
    id serial primary key,
    message_id varchar(512) not null,
    date timestamp not null,
    dsn varchar(16) not null,
    delay integer not null default 0,
    status varchar(64) not null default 'N.D.',
    status_desc text not null default '',
    mailto varchar(256) not null default 'N.D.',
    ref varchar(256) not null default ''
);
create index idx_mail_log_message_id on mail_log (message_id);
create index idx_mail_log_date on mail_log (date);
create index idx_mail_log_mailto on mail_log (mailto);
create index idx_mail_log_ref on mail_log (ref);
