-- MEDIA INFO
CREATE SEQUENCE media_id_sequence
    START WITH 1
    INCREMENT BY 1
    MINVALUE 1
    MAXVALUE 9223372036854775807
    CACHE 1;

CREATE FUNCTION get_next_media() RETURNS bigint AS $$
SELECT nextval('media_id_sequence') as result;
$$ LANGUAGE sql;

CREATE FUNCTION get_curr_media() RETURNS bigint AS $$
SELECT lastvalue as results from media_id_sequence;
$$ LANGUAGE sql;
