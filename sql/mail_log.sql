create table mail_log_in (
    id serial primary key,
    mailfrom varchar(256),
    message_id varchar(512) not null,
    r_date timestamp not null,
    mail_size integer not null default 0,
    nrcpts smallint not null default 0,
    ref varchar(256) not null
);

create index idx_mail_log_in_ref on mail_log_in using hash (ref);
create index idx_mail_log_message_id on mail_log_in using hash (message_id);
create index idx_mail_log_r_date on mail_log_in using btree (r_date);

create table mail_log_out (
    mail_id integer not null references mail_log_in(id),
    d_date timestamp not null,
    dsn varchar(16) not null,
    relay varchar(256) not null,
    delay numeric not null default 0,
    status varchar(64) not null default 'unknown',
    status_desc text not null default '',
    mailto varchar(256)
);

create index idx_mail_log_out_mail_id on mail_log_out using btree (mail_id);
create index idx_mail_log_out_d_date on mail_log_out using btree (d_date);
create index idx_mail_log_out_mailto on mail_log_out using btree (mailto);
